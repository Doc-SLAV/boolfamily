import asyncio
import aiohttp
import urllib.parse
import logging
import json
import random
from datetime import datetime, timedelta

# Mengatur level logging ke INFO
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_URL = "https://bot-api.bool.network/bool-tg-interface"
MINIAPP_BASE_URL = "https://miniapp.bool.network/backend/bool-tg-interface"
RPC_URL = "https://betatest-rpc-node-http.bool.network/"

API_ENDPOINTS = {
    "user_strict": f"{BASE_URL}/user/user/strict",
    "assignment_list": f"{BASE_URL}/assignment/list",
    "daily_list": f"{BASE_URL}/assignment/daily/list",
    "repeat_assignment": f"{BASE_URL}/assignment/daily/repeat-assignment",
    "perform_task": f"{BASE_URL}/assignment/do",
    "daily_do": f"{BASE_URL}/assignment/daily/do",
    "stake_do": f"{BASE_URL}/stake/do",
    "staking_devices": f"{MINIAPP_BASE_URL}/user/vote:devices",
    "user_staked_devices": f"{MINIAPP_BASE_URL}/user/user-vote-devices"
}

HEADERS = {
    "default": {
        "accept": "application/json",
        "content-type": "application/json",
        "Referer": "https://miniapp.bool.network/",
    },
    "options": {
        "accept": "*/*",
        "Referer": "https://miniapp.bool.network/",
    }
}

async def make_request(url, http_client, method="POST", payload=None, headers=None, max_retries=3, delay=5, expect_json=True):
    retries = 0
    while retries < max_retries:
        try:
            log_full_request = True
            if any(endpoint in url for endpoint in ["assignment/do", "assignment/daily/list", "assignment/daily/repeat-assignment"]):
                log_full_request = False

            if log_full_request:
                logging.debug(f"Making request to {url} with payload: {payload}")
            else:
                logging.debug(f"Making request to {url}")

            if method == "POST":
                async with http_client.post(url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    if expect_json:
                        json_response = await response.json()
                        if log_full_request:
                            logging.debug(f"Received response: {json_response}")
                        return json_response
                    else:
                        text_response = await response.text()
                        if log_full_request:
                            logging.debug(f"Received response: {text_response}")
                        return text_response
            elif method == "OPTIONS":
                async with http_client.options(url, headers=headers) as response:
                    response.raise_for_status()
                    return await response.text()
            else:
                async with http_client.get(url, headers=headers) as response:
                    response.raise_for_status()
                    if expect_json:
                        json_response = await response.json()
                        if log_full_request:
                            logging.debug(f"Received response: {json_response}")
                        return json_response
                    else:
                        text_response = await response.text()
                        if log_full_request:
                            logging.debug(f"Received response: {text_response}")
                        return text_response
        except aiohttp.ContentTypeError as e:
            logging.error(f"Error parsing response from {url}: {e}")
            return None
        except aiohttp.ClientResponseError as e:
            if e.status == 500:
                retries += 1
                logging.error(f"500 Server Error: Retrying {retries}/{max_retries} after {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                logging.error(f"Error making request to {url}: {e}")
                return None
        except Exception as e:
            logging.error(f"Error making request to {url}: {e}")
            return None
    logging.error(f"Failed to complete request after {max_retries} retries.")
    return None

def load_session_data(file_path):
    session_data_list = []
    with open(file_path, "r") as file:
        for line in file:
            params = urllib.parse.parse_qs(line.strip())
            session_data = {
                "query_id": params["query_id"][0],
                "user": params["user"][0],
                "auth_date": params["auth_date"][0],
                "hash": params["hash"][0],
                "data": f"auth_date={params['auth_date'][0]}\nquery_id={params['query_id'][0]}\nuser={urllib.parse.unquote(params['user'][0])}"
            }
            session_data_list.append(session_data)
    return session_data_list

async def visit_rum(http_client):
    rum_url = "https://cloudflareinsights.com/cdn-cgi/rum"
    rum_payload = {
        "resources": [],
        "referrer": "https://miniapp.bool.network/stake",
        "eventType": 1,
        "firstPaint": 317,
        "firstContentfulPaint": 317,
        "startTime": 1727788359339.4,
        "versions": {"js": "2024.6.1", "timings": 1},
        "pageloadId": "08d3ddd0-63d9-4f42-94ca-f73f84ad3274",
        "location": "https://miniapp.bool.network/home",
        "nt": "reload",
        "timingsV2": {"nextHopProtocol": "h2", "transferSize": 41182, "decodedBodySize": 318601},
        "dt": "",
        "siteToken": "488f8ada2bda4fd6a5174b8d48c3e48c",
        "st": 2
    }
    await make_request(rum_url, http_client, method="POST", payload=rum_payload, expect_json=False)
    logging.info("Visited RUM")

async def get_user_info(session_data, http_client):
    payload = {"data": session_data["data"], "hash": session_data["hash"]}
    user_response = await make_request(API_ENDPOINTS["user_strict"], http_client, payload=payload, headers=HEADERS["default"])
    if user_response and user_response.get("code") == 200:
        return user_response.get('data', {})
    else:
        logging.error("Failed to fetch user information.")
        return None

async def check_daily_tasks(session_data, http_client, username):
    logging.info(f"Checking daily tasks for user: {username}")
    payload = {"data": session_data["data"], "hash": session_data["hash"]}

    # Melakukan preflight OPTIONS request sebelum daily_list
    await make_request(API_ENDPOINTS["daily_list"], http_client, method="OPTIONS", headers=HEADERS["options"])

    daily_response = await make_request(API_ENDPOINTS["daily_list"], http_client, payload=payload, headers=HEADERS["default"])
    if daily_response and daily_response.get("code") == 200:
        daily_tasks = daily_response.get('data', [])
        for task in daily_tasks:
            assignment_id = task['assignmentId']
            if not task.get('done', False):
                # Melakukan preflight OPTIONS request sebelum mengerjakan tugas daily login
                await make_request(API_ENDPOINTS["daily_do"], http_client, method="OPTIONS", headers=HEADERS["options"])
                logging.info(f"Performing daily login task: {assignment_id} - {task['title']}")
                task_payload = {
                    "assignmentId": assignment_id,
                    "data": session_data["data"],
                    "hash": session_data["hash"]
                }
                task_response = await make_request(API_ENDPOINTS["daily_do"], http_client, payload=task_payload, headers=HEADERS["default"])
                if task_response and task_response.get('code') == 200:
                    logging.info(f"Daily login task {assignment_id} completed successfully.")
                    # Memastikan tugas sudah selesai dengan memeriksa ulang status tugas
                    daily_check_response = await make_request(API_ENDPOINTS["daily_list"], http_client, payload=payload, headers=HEADERS["default"])
                    if daily_check_response and daily_check_response.get("code") == 200:
                        updated_tasks = daily_check_response.get('data', [])
                        for updated_task in updated_tasks:
                            if updated_task['assignmentId'] == assignment_id and updated_task.get('done', False):
                                logging.info(f"Task {assignment_id} is confirmed completed.")
                    # Menampilkan balance rewardValue setelah daily login
                    user_info = await get_user_info(session_data, http_client)
                    if user_info:
                        reward_value = user_info.get('rewardValue', '0')
                        logging.info(f"User {username} has a reward value of {reward_value} tBOL (different from blockchain balance).")
                else:
                    logging.error(f"Failed to complete daily login task {assignment_id}. Response: {task_response}")
                await asyncio.sleep(5)
            else:
                logging.info(f"Daily login task {assignment_id} already completed.")
    else:
        logging.error("Failed to fetch tasks from daily list.")

    # Melakukan preflight OPTIONS request sebelum repeat_assignment
    await make_request(API_ENDPOINTS["repeat_assignment"], http_client, method="OPTIONS", headers=HEADERS["options"])

    repeat_response = await make_request(API_ENDPOINTS["repeat_assignment"], http_client, payload=payload, headers=HEADERS["default"])
    if repeat_response and repeat_response.get("code") == 200:
        repeat_tasks = repeat_response.get('data', [])
        for task in repeat_tasks:
            assignment_id = task['assignmentId']
            if not task.get('done', False):
                # Melakukan preflight OPTIONS request sebelum mengerjakan tugas
                await make_request(API_ENDPOINTS["daily_do"], http_client, method="OPTIONS", headers=HEADERS["options"])
                logging.info(f"Performing repeat assignment task: {assignment_id} - {task['title']}")
                task_payload = {
                    "assignmentId": assignment_id,
                    "data": session_data["data"],
                    "hash": session_data["hash"]
                }
                task_response = await make_request(API_ENDPOINTS["daily_do"], http_client, payload=task_payload, headers=HEADERS["default"])
                if task_response and task_response.get('code') == 200:
                    logging.info(f"Repeat assignment task {assignment_id} completed successfully.")
                else:
                    logging.error(f"Failed to complete repeat assignment task {assignment_id}. Response: {task_response}")
                await asyncio.sleep(5)
            else:
                logging.info(f"Repeat assignment task {assignment_id} already completed.")
    else:
        logging.error("Failed to fetch tasks from repeat assignment.")

async def perform_task(session_data, http_client, username):
    logging.info(f"Fetching regular tasks for user: {username}")
    payload = {"data": session_data["data"], "hash": session_data["hash"]}

    # Melakukan preflight OPTIONS request sebelum assignment_list
    await make_request(API_ENDPOINTS["assignment_list"], http_client, method="OPTIONS", headers=HEADERS["options"])

    task_data = await make_request(API_ENDPOINTS["assignment_list"], http_client, payload=payload, headers=HEADERS["default"])
    if task_data and task_data.get("code") == 200:
        tasks = task_data.get('data', [])
        for task in tasks:
            assignment_name = task.get('title', 'Unnamed Task')
            assignment_id = task['assignmentId']
            if not task.get('done', False) and "join tg channel" not in assignment_name.lower():
                # Melakukan preflight OPTIONS request sebelum mengerjakan tugas
                await make_request(API_ENDPOINTS["perform_task"], http_client, method="OPTIONS", headers=HEADERS["options"])
                logging.info(f"Performing task {assignment_id} - {assignment_name}")
                task_payload = {"assignmentId": assignment_id, "data": session_data["data"], "hash": session_data["hash"]}
                task_response = await make_request(API_ENDPOINTS["perform_task"], http_client, payload=task_payload, headers=HEADERS["default"])
                if task_response and task_response.get('code') == 200:
                    logging.info(f"Task {assignment_id} - {assignment_name} completed successfully.")
                else:
                    logging.error(f"Failed to complete task {assignment_id} - {assignment_name}. Response: {task_response}")
                await asyncio.sleep(5)
            else:
                logging.info(f"Task {assignment_id} - {assignment_name} already completed or skipped.")
    else:
        logging.error("No tasks available.")

async def fetch_balance_and_chain_id(evm_address, http_client):
    payload = [
        {"method": "eth_chainId", "params": [], "id": 1, "jsonrpc": "2.0"},
        {"method": "eth_getBalance", "params": [evm_address, "latest"], "id": 2, "jsonrpc": "2.0"}
    ]
    response = await make_request(RPC_URL, http_client, payload=payload)
    if response:
        balance_hex = response[1]["result"]
        balance_bool = int(balance_hex, 16) / (10 ** 18)
        return balance_bool
    return 0

async def get_staking_device(session_data, evm_address, http_client, username):
    logging.info(f"Fetching staking devices for user: {username}")
    staking_data = await make_request(API_ENDPOINTS["staking_devices"], http_client, method="GET")
    all_devices = staking_data.get('data', {}).get('records', [])
    params = {
        "address": evm_address,
        "pageNo": 1,
        "pageSize": 100,
        "yield": 1
    }
    user_staked_url = f"{API_ENDPOINTS['user_staked_devices']}?{urllib.parse.urlencode(params)}"
    user_staked_data = await make_request(user_staked_url, http_client, method="GET")
    user_staked_devices = user_staked_data.get('data', {}).get('records', [])
    user_staked_device_ids = [device['deviceID'] for device in user_staked_devices]
    available_devices = [device for device in all_devices if device['deviceID'] not in user_staked_device_ids and device['deviceState'] == 'SERVING']
    if available_devices:
        selected_device = random.choice(available_devices)
        logging.info(f"Selected staking device: {selected_device['deviceID']} with voter count {selected_device['voterCount']}")
        return selected_device
    else:
        logging.error("No valid staking devices available after filtering out already staked devices.")
        return None

async def perform_staking(session_data, device, http_client, username):
    payload = {
        "deviceId": [device['deviceID']],
        "amount": ["200"],
        "data": session_data["data"],
        "hash": session_data["hash"]
    }
    response = await make_request(API_ENDPOINTS["stake_do"], http_client, payload=payload)
    if response and response.get('message') == 'success':
        logging.info(f"Staking successful on device {device['deviceID']}")
        if 'data' in response:
            raw_transaction = response['data']
            logging.info(f"Sending raw transaction.")
            tx_payload = {
                "method": "eth_sendRawTransaction",
                "params": [raw_transaction],
                "id": 1,
                "jsonrpc": "2.0"
            }
            tx_response = await make_request(RPC_URL, http_client, payload=tx_payload)
            if 'result' in tx_response:
                logging.info(f"Transaction Hash: {tx_response['result']}")
            else:
                logging.error("Failed to send transaction, no transaction hash returned.")
        else:
            logging.error("No raw transaction data returned, staking might not be completed.")
    else:
        logging.error(f"Staking failed on device {device['deviceID']}. Response: {response}")

async def check_balance_and_stake(session_data, username, http_client):
    logging.info(f"Fetching strict data for user: {username}")
    strict_data = await make_request(API_ENDPOINTS["user_strict"], http_client, payload={"data": session_data["data"], "hash": session_data["hash"]}, headers=HEADERS["default"])
    if strict_data and strict_data.get('code') == 200:
        evm_address = strict_data['data']['evmAddress']
        logging.info(f"User {username} EVM Address: {evm_address}")
        logging.info(f"Fetching blockchain balance for EVM address: {evm_address}")
        balance_bool = await fetch_balance_and_chain_id(evm_address, http_client)
        logging.info(f"Blockchain Balance for {username}: {balance_bool} BOOL")
        if balance_bool > 200:
            device = await get_staking_device(session_data, evm_address, http_client, username)
            if device:
                await perform_staking(session_data, device, http_client, username)
            else:
                logging.error(f"No valid staking devices for user {username}.")
        else:
            logging.info(f"Not enough balance to stake for user {username}. Current balance: {balance_bool}")
    else:
        logging.error(f"Failed to fetch strict data for user {username}.")

async def process_session(session_data, http_client):
    user_info = json.loads(urllib.parse.unquote(session_data["user"]))
    username = user_info.get("username", "Unknown")
    logging.info(f"Processing session for user: {username}")
    await visit_rum(http_client)  # Menjalankan RUM di awal untuk menghindari error 500
    await check_daily_tasks(session_data, http_client, username)
    await perform_task(session_data, http_client, username)
    await check_balance_and_stake(session_data, username, http_client)

def time_until_midnight_utc():
    now = datetime.utcnow()
    midnight_utc = (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
    return (midnight_utc - now).total_seconds()

def format_seconds_to_hms(seconds):
    hours = int(seconds) // 3600
    minutes = (int(seconds) % 3600) // 60
    seconds = int(seconds) % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

async def main():
    while True:
        session_data_list = load_session_data('sesi.txt')
        async with aiohttp.ClientSession() as http_client:
            for session_data in session_data_list:
                await process_session(session_data, http_client)
                await asyncio.sleep(5)
        seconds_until_midnight = time_until_midnight_utc()
        countdown = format_seconds_to_hms(seconds_until_midnight)
        logging.info(f"Waiting {countdown} until 00:01 UTC to restart...")
        await asyncio.sleep(seconds_until_midnight)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Script terminated by user.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
