import json
import psutil

from flask import Flask, jsonify, render_template
from flask_apscheduler import APScheduler


class Config(object):
    SCHEDULER_API_ENABLED = True
    DUMP_PATH = "connections.json"


app = Flask(__name__, template_folder="")
scheduler = APScheduler()


@app.route("/")
def netstatgraph():
    return render_template("dashboard.html")


@app.route("/update", methods=['POST'])
def update():
    with open(app.config["DUMP_PATH"], "r", encoding="utf-8") as dump_f:
        content = json.load(dump_f)
    # print(content)
    return jsonify(content)


@scheduler.task('interval', id="dump_netstat", seconds=5)
def get_remote_connections():
    connections = {}
    for p in psutil.net_connections(kind='inet'):
        try:
            remoteip, remoteport = p.raddr
            pid = p.pid
            status = p.status
            gist_key = f"{pid}/{remoteip}:{remoteport}/{status}"
            if connections.get(gist_key, None):
                connections[gist_key]['count'] += 1
            else:
                connection_data = {
                    "pid": pid,
                    "ip": remoteip,
                    "port": remoteport,
                    "status": status,
                    "count": 1,
                }
                connections[gist_key] = connection_data
        except ValueError:
            pass
        except Exception as e:
            print(f"---\t[!]\t---\t{type(e)} parsing net_connections:\n{e}\n")
    unique_connections = [value for key, value in connections.items()]
    with open(app.config["DUMP_PATH"], "w", encoding='utf-8') as dump_f:
        json.dump(unique_connections, dump_f)
    print(f"Dumped {len(connections)} connections to {app.config['DUMP_PATH']}")


if __name__ == "__main__":
    app.config.from_object(Config())

    scheduler.init_app(app)
    scheduler.start()

    app.run()
