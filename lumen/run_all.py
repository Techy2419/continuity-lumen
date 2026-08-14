import threading

from services import encoding_app, playback_app, ingest_app, recommendation_app
import control_app
import simulator
import config


def main():
    simulator.start()

    threading.Thread(target=encoding_app.run, daemon=True).start()
    threading.Thread(target=playback_app.run, daemon=True).start()
    threading.Thread(target=ingest_app.run, daemon=True).start()
    threading.Thread(target=recommendation_app.run, daemon=True).start()

    print("Lumen mock backend running.")
    print(f"  Encoding metrics:       http://localhost:{config.ENCODING_PORT}/metrics")
    print(f"  Playback metrics:       http://localhost:{config.PLAYBACK_PORT}/metrics")
    print(f"  Ingest metrics:         http://localhost:{config.INGEST_PORT}/metrics")
    print(f"  Recommendation metrics: http://localhost:{config.RECOMMENDATION_PORT}/metrics")
    print(f"  Control/incidents API:  http://localhost:{config.CONTROL_PORT}")
    print()
    print("Trigger an incident:")
    print(f'  curl -X POST http://localhost:{config.CONTROL_PORT}/incidents/trigger '
          '-H "Content-Type: application/json" -d \'{"name": "encoding_crash"}\'')
    print()

    control_app.run()  # blocks main thread


if __name__ == "__main__":
    main()
