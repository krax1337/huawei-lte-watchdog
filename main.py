import time
import os
import schedule
import logging
import sys
from pythonping import ping as ping_host
from datetime import datetime
from huawei_lte_api.AuthorizedConnection import AuthorizedConnection
from huawei_lte_api.Client import Client
from dotenv import load_dotenv
from prometheus_client import start_http_server, Gauge, Info

FORMAT = '[%(asctime)s] %(levelname)s - %(message)s'
logging.basicConfig(format=FORMAT, stream=sys.stdout, level=logging.INFO)

SINR = Gauge('SINR', 'SINR')
RSPQ = Gauge('RSPQ', 'RSPQ')
RSRP = Gauge('RSRP', 'RSRP')
UPLOAD = Gauge('UPLOAD', 'UPLOAD')
DOWNLOAD = Gauge('DOWNLOAD', 'DOWNLOAD')
CURRENT_CELL = Info('CURRENT_CELL', 'CURRENT_CELL')
CURRENT_BAND = Info('CURRENT_BAND', 'CURRENT_BAND')

load_dotenv()


def reboot():
    logging.info("Reboot initialized")
    connection = AuthorizedConnection(ADDRESS, USER, PASSWORD)
    client = Client(connection)
    client.device.reboot()
    time.sleep(90)


CELL = int(os.environ["LTE_CELL"])
BANDS = str(os.environ["LTE_BANDS"])
CHANGE_TYPE = str(os.environ["LTE_CHANGE_TYPE"])
ADDRESS = str(os.environ["LTE_ADDRESS"])
USER = str(os.environ["LTE_USER"])
PASSWORD = str(os.environ["LTE_PASSWORD"])
TIME = str(os.environ["REBOOT_TIME"])
PING_TIMEOUT = str(os.environ["PING_TIMEOUT"])
MONITOR_ONLY = bool(int(os.environ["MONITOR_ONLY"]))

BANDS_LIST = [
    ('1', '2100', 1),
    ('2', '1900', 2),
    ('3', '1800', 4),
    ('4', '1700', 8),
    ('5', '850', 10),
    ('6', '800', 20),
    ('7', '2600', 40),
    ('8', '900', 80),
    ('19', '850', 40000),
    ('20', '800', 80000),
    ('26', '850', 2000000),
    ('28', '700', 8000000),
    ('32', '1500', 80000000),
    ('38', '2600', 2000000000),
    ('40', '2300', 8000000000),
    ('41', '2500', 10000000000),
    ('42', '3500', 20000000000),
]


def band_calculation(settled_bands):
    settled_bands = settled_bands.split("+")
    settled_bands_hex = []

    for var in settled_bands:
        for band in BANDS_LIST:
            if var == band[0]:
                settled_bands_hex.append(band[2])

    return settled_bands_hex[0], sum(settled_bands_hex)


def remove_zeros_and_convert_to_int(input_str):
    return int(''.join(filter(lambda x: x != '0', str(input_str))))


first_band, sum_band = band_calculation(BANDS)

networkband = "3FFFFFFF"
networkmode = "03"

connection = None

schedule.every().day.at(TIME).do(reboot)

if __name__ == '__main__':
    logging.info("Service started")
    start_http_server(9995)

    if (MONITOR_ONLY):
        logging.info("Monitor only mode")

    if (CHANGE_TYPE != "SEQ" and CHANGE_TYPE != "ALL"):
        logging.error("Wrong LTE_CHANGE_TYPE must be SEQ or ALL")
        sys.exit()

    while True:
        schedule.run_pending()
        try:
            if (connection is None):
                connection = AuthorizedConnection(ADDRESS, USER, PASSWORD)
                client = Client(connection)
            elif(len(client.monitoring.traffic_statistics()) < 2):
                raise Exception("Router is not reachable")
        except Exception as e:
            logging.error(f"Exception - {e}")
            time.sleep(60)
            continue

        ping_result = ping_host('1.1.1.1', timeout=int(PING_TIMEOUT))
        if (not ping_result.success() and not MONITOR_ONLY and len(client.monitoring.traffic_statistics()) > 1):
            logging.info("Reboot initialized because of no internet")
            client.device.reboot()
            time.sleep(90)
            continue

        bdw = client.monitoring.traffic_statistics()
        current_cell = int(client.device.signal()["cell_id"])
        current_band = client.net.net_mode()["LTEBand"]
        signal = client.device.signal()
        download = int(bdw['CurrentDownloadRate'])*8//(1024*1024)
        upload = int(bdw['CurrentUploadRate'])*8//(1024*1024)

        SINR.set(float(signal["sinr"].replace("dB", "")))
        RSPQ.set(float(signal["rsrq"].replace("dB", "")))
        RSRP.set(float(signal["rsrp"].replace("dBm", "")))
        DOWNLOAD.set(download)
        UPLOAD.set(upload)
        CURRENT_CELL.info({'current_cell': str(current_cell)})
        CURRENT_BAND.info({'current_band': current_band})

        logging.info(f'Current cell: {current_cell} Current band: {
                     current_band} | RSRQ: {signal["rsrq"]}   SINR: {signal["sinr"]}')

        if not MONITOR_ONLY and current_cell != CELL or (remove_zeros_and_convert_to_int(current_band) != remove_zeros_and_convert_to_int(sum_band)):
            if current_cell > 0 and current_band != "0" and current_cell != 0:
                temp_cell = 0
                cnt = 1
                logging.info("Reconnection initialized")
                logging.info(f"Target cell: {
                    CELL} - Target bands: {BANDS} - Change type: {CHANGE_TYPE}")

                while temp_cell != CELL:
                    if (CHANGE_TYPE == "ALL"):
                        client.net.set_net_mode(
                            sum_band, networkband, networkmode)
                        time.sleep(10)
                        temp_cell = int(client.device.signal()["cell_id"])
                        logging.info(f"Attempt number: {
                                     cnt} | Temporary cell: {temp_cell}")
                        cnt += 1
                    elif (CHANGE_TYPE == "SEQ"):
                        client.net.set_net_mode(
                            first_band, networkband, networkmode)
                        time.sleep(10)
                        client.net.set_net_mode(
                            sum_band, networkband, networkmode)
                        time.sleep(10)
                        temp_cell = int(client.device.signal()["cell_id"])
                        logging.info(f"Attempt number: {
                                     cnt} | Temporary cell: {temp_cell}")
                        cnt += 1

                logging.info(f"Reconnection completed")

        time.sleep(1)
