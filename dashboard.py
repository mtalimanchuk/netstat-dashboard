import datetime
import json
import psutil

from flask import Flask, jsonify, render_template, request
from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy


class Config(object):
    SCHEDULER_API_ENABLED = True
    DUMP_PATH = "connections.json"
    SQLALCHEMY_DATABASE_URI = 'sqlite:///test.db'


app = Flask(__name__, template_folder="")
app.config.from_object(Config())
scheduler = APScheduler()
db = SQLAlchemy(app)


class Process(db.Model):
    __tablename__ = "process"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String)
    started = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean)
    connections = db.relationship("Connection", backref="process", lazy=True)

    def __init__(self, id, name, started):
        self.id = id
        self.name = name
        self.started = started
        self.is_active = True

    @staticmethod
    def check_in(id, name, started):
        existing_process = Process.query.filter_by(id=id).first()
        if existing_process:
            # print("It's a known process")
            existing_process.name = name
            existing_process.started = started
            existing_process.is_active = True
        else:
            # print("It's a new process")
            new_process = Process(id=id, name=name, started=started)
            db.session.add(new_process)
        db.session.commit()

    @staticmethod
    def reset_activity_flag():
        for p in Process.query.all():
            p.is_active = False
        db.session.commit()
        # print(f"Deactivated all processes")

    @staticmethod
    def read_timestamp(timestamp_string):
        try:
            return datetime.datetime.strptime("2019-12-29 00:22:28", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            today = datetime.datetime.now()
            return Process.read_timestamp(f"{today:%Y-%m-%d} {timestamp_string}")


class Connection(db.Model):
    __tablename__ = "connection"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ip = db.Column(db.String, nullable=False)
    port = db.Column(db.String, nullable=False)
    status = db.Column(db.String, nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey("process.id"), nullable=True)
    first_seen = db.Column(db.DateTime, nullable=False)
    last_seen = db.Column(db.DateTime, nullable=False)

    def __init__(self, ip, port, status, pid):
        self.ip = ip
        self.port = port
        self.status = status
        self.process_id = pid
        self.first_seen = datetime.datetime.now()
        self.last_seen = self.first_seen

    @staticmethod
    def check_in(ip, port, status, pid):
        existing_connection = Connection.query.filter_by(ip=ip, port=port).first()
        if existing_connection:
            existing_connection.status = status
            existing_connection.pid = pid
            existing_connection.last_seen = datetime.datetime.now()
        else:
            new_connection = Connection(ip=ip, port=port, status=status, pid=pid)
            db.session.add(new_connection)
        db.session.commit()


@app.route("/")
def netstatgraph():
    return render_template("dashboard.html")


@app.route("/update", methods=['POST'])
def update():
    pinned_ips = request.get_json(force=True)
    pinned = []
    for conn in Connection.query.filter(Connection.ip.in_(pinned_ips)):
        conn_dict = {c.name: getattr(conn, c.name) for c in conn.__table__.columns}
        conn_dict['first_seen'] = f"{conn_dict['first_seen']:%d %m %Y %H:%M:%S}"
        conn_dict['last_seen'] = f"{conn_dict['last_seen']:%d %m %Y %H:%M:%S}"
        pinned.append(conn_dict)

    connections = []
    for conn in Connection.query.all():
        conn_dict = {c.name: getattr(conn, c.name) for c in conn.__table__.columns}
        connections.append(conn_dict)

    print([pinned, connections])
    return jsonify([pinned, connections])


@scheduler.task('interval', id="dump_netstat", seconds=5)
def get_remote_connections():
    Process.reset_activity_flag()
    for p in psutil.process_iter(attrs=['pid', 'name', 'create_time']):
        create_time = datetime.datetime.fromtimestamp(p.info['create_time'])
        Process.check_in(p.info['pid'], p.info['name'], create_time)
    print("Got new processes")

    for p in psutil.net_connections(kind='inet'):
        try:
            ip, port = p.raddr
            status = p.status
            pid = p.pid
            Connection.check_in(ip, port, status, pid)
        except ValueError:
            pass
        except Exception as e:
            print(f"---\t[!]\t---\t{type(e)} parsing net_connections:\n{e}\n")
    # print("Got connections")


if __name__ == "__main__":
    db.create_all()

    scheduler.init_app(app)
    scheduler.start()

    app.run()
