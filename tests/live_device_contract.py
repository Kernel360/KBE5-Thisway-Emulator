"""Called by BE emulatorClientTest against its disposable Boot/MySQL fixture."""
import os
import sys

from models.emulator_data import GpsLogRequest, PowerLogRequest, GeofenceLogRequest
from services.log_handlers.gps_log_handler import GpsLogHandler
from services.log_handlers.power_log_handler import PowerLogHandler
from services.log_handlers.geofence_log_handler import GeofenceLogHandler


def main():
    base = os.environ["TEST_BACKEND_URL"]
    if sys.argv[1] == "hour-boundary":
        from datetime import datetime, timedelta
        from services.log_handlers.gps_log_handler import KST
        handler = GpsLogHandler(backend_url=base)
        start = datetime(2020, 1, 1, 23, 59, 58, tzinfo=KST)
        points = [dict(timestamp=start + timedelta(seconds=i), latitude=37, longitude=127,
                       speed=0, heading=0, accumulated_distance=100, battery_level=90, gcd="A") for i in range(5)]
        packets = handler.batch_gps_data_points(os.environ["TEST_MDN"], points,
                    dict(terminal_id="1", manufacture_id=1, packet_version=1, device_id=1))
        if [p.cCnt for p in packets] != ["2", "3"]:
            raise RuntimeError("Unexpected GPS split")
        for packet in packets:
            if not handler.send_log_to_backend(packet)[0]:
                raise RuntimeError("GPS boundary request rejected")
        print("hour boundary verified")
        return
    common = dict(mdn=os.environ["TEST_MDN"], tid="1", mid="1", pv="1", did="1", gcd="A",
                  lat="37000000", lon="127000000", ang="0", spd="0", sum="100")
    packets = [
        (GpsLogHandler(backend_url=base), GpsLogRequest(**common, oTime="20200101102000", cCnt="1",
             cList=[dict(sec="30", gcd="A", lat="37000000", lon="127000000", ang="0", spd="0", sum="100", bat="12")])),
        (PowerLogHandler(backend_url=base), PowerLogRequest(**common, onTime="20200101102000")),
        (GeofenceLogHandler(backend_url=base), GeofenceLogRequest(**common, oTime="20200101102000", geoGrpId="1", geoPId="1", evtVal="1")),
    ]
    expected = sys.argv[1] == "accepted"
    for handler, packet in packets:
        success, message = handler.send_log_to_backend(packet)
        if success != expected or (not expected and not message.startswith("Device authentication rejected")):
            raise RuntimeError("Unexpected telemetry contract result")
    print("3 telemetry contracts verified")


if __name__ == "__main__":
    main()
