import os
import time
from web3 import Web3
from web3.middleware import geth_poa_middleware
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from typing import List, Optional
from datetime import datetime
import sys

# 常量定义
VOTING_CONTRACT_ADDRESS = '0x672e69f8ED6eA070f5722d6c77940114cc901938'  # 投票合约地址
FAUCET_CONTRACT_ADDRESS = '0x43808E0766f88332535FF8326F52e4734de35F0e'  # 水龙头合约地址
VOTING_TOKEN_ADDRESS = '0x3E933b66904F83b6E91a9511877C99b43584adA3'    # 投票代币地址
RPC_URL = 'https://base-sepolia-rpc.publicnode.com'  # RPC 接口地址
CHAIN_ID = 84532  # 链 ID

# ABI 定义
VOTING_CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32[]", "name": "votingProjectIds", "type": "bytes32[]"},
            {"internalType": "uint256[]", "name": "votes", "type": "uint256[]"}
        ],
        "name": "voteOnProjects",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

FAUCET_CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "address[]", "name": "tokenAddresses", "type": "address[]"}
        ],
        "name": "claimTokens",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

PROJECT_IDS_TO_VOTE = [
    "0xe5d033db611ae3f5682ace7285860a6ceb1195d5f80f2721a82d4baff67daddb",
    "0xb99bb4429ce45c2cf000bc98f847741c88603e234f6099d78fe47c2b50738776",
    "0x8689005e34728a5f6027d7c12bd49ef51fa54d62971bf6e5490fbaaaf85a1e21",
    "0xf712336c9a04915c7b25b30412d0fb8613a417cd8a94f00ca0b2da73e1704949"
]

VOTE_DISTRIBUTIONS = [
    Web3.to_wei(4, 'ether'),
    Web3.to_wei(2, 'ether'),
    Web3.to_wei(2, 'ether'),
    Web3.to_wei(2, 'ether'),
]

TOTAL_VOTE_AMOUNT = sum(VOTE_DISTRIBUTIONS)

TOKENS_TO_CLAIM_FROM = [
    "0xEa347A7CB535cBE125099A4C3B992149aE08e55d",
    "0xB9e5D51908CCF86d91443e61a4C9d8e4FeE27e33",
    "0x3E933b66904F83b6E91a9511877C99b43584adA3"
]

# 读取私钥和代理
def read_private_keys() -> List[str]:
    try:
        with open('privatekey.txt', 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"读取私钥出错: {e}")
        return []

def read_proxies() -> List[str]:
    try:
        with open('proxy.txt', 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"读取代理出错: {e}")
        return []

# 创建带有代理的 Web3 实例
def create_web3_with_proxy(proxy: Optional[str] = None) -> Web3:
    if proxy:
        # 处理代理格式
        if 'socks' in proxy.lower():
            from web3.contrib.socks import SOCKSProxyManager
            w3 = Web3(SOCKSProxyManager(proxy, RPC_URL))
        else:
            session = requests.Session()
            session.proxies = {'http': proxy, 'https': proxy}
            w3 = Web3(Web3.HTTPProvider(RPC_URL, session=session))
    else:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
    
    # 添加 PoA 中间件（适用于 Base Sepolia 等网络）
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3

# 批准代币用于投票
async def approve_tokens_for_voting(private_key: str, proxy: Optional[str]) -> bool:
    try:
        w3 = create_web3_with_proxy(proxy)
        account = w3.eth.account.from_key(private_key)
        token_contract = w3.eth.contract(address=VOTING_TOKEN_ADDRESS, abi=ERC20_ABI)
        
        print(f"检查账户 {account.address} 的授权额度")
        current_allowance = token_contract.functions.allowance(account.address, VOTING_CONTRACT_ADDRESS).call()
        print(f"当前授权额度: {Web3.from_wei(current_allowance, 'ether')} 个代币")

        if current_allowance >= TOTAL_VOTE_AMOUNT:
            print("授权额度已足够，无需再次授权。")
            return True

        gas_limit = 100000
        print(f"正在为投票合约授权 {Web3.from_wei(TOTAL_VOTE_AMOUNT, 'ether')} 个代币...")
        approve_amount = TOTAL_VOTE_AMOUNT * 2
        tx = token_contract.functions.approve(VOTING_CONTRACT_ADDRESS, approve_amount).build_transaction({
            'from': account.address,
            'gas': gas_limit,
            'nonce': w3.eth.get_transaction_count(account.address),
            'chainId': CHAIN_ID
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(f"授权交易已提交: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 0:
            print("授权交易失败！")
            return False
        
        print(f"授权交易确认成功！使用Gas: {receipt.gasUsed}")
        return True
    except Exception as e:
        print(f"授权代币出错: {e}")
        return False

# 执行投票
async def vote_on_projects(private_key: str, proxy: Optional[str]) -> bool:
    try:
        w3 = create_web3_with_proxy(proxy)
        account = w3.eth.account.from_key(private_key)
        contract = w3.eth.contract(address=VOTING_CONTRACT_ADDRESS, abi=VOTING_CONTRACT_ABI)

        print(f"从地址 {account.address} 执行项目投票")
        for i, (proj_id, votes) in enumerate(zip(PROJECT_IDS_TO_VOTE, VOTE_DISTRIBUTIONS), 1):
            print(f"项目 {i}: {proj_id} - {Web3.from_wei(votes, 'ether')} 个代币")

        if not await approve_tokens_for_voting(private_key, proxy):
            print("授权代币失败，取消投票。")
            return False

        gas_limit = 3000000
        tx = contract.functions.voteOnProjects(PROJECT_IDS_TO_VOTE, VOTE_DISTRIBUTIONS).build_transaction({
            'from': account.address,
            'gas': gas_limit,
            'nonce': w3.eth.get_transaction_count(account.address),
            'chainId': CHAIN_ID
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(f"投票交易已提交: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 0:
            print("投票交易失败！")
            return False
        
        print(f"投票交易确认成功！使用Gas: {receipt.gasUsed}")
        return True
    except Exception as e:
        print(f"投票项目出错: {e}")
        return False

# 领取代币
async def claim_tokens(private_key: str, proxy: Optional[str]) -> bool:
    try:
        w3 = create_web3_with_proxy(proxy)
        account = w3.eth.account.from_key(private_key)
        contract = w3.eth.contract(address=FAUCET_CONTRACT_ADDRESS, abi=FAUCET_CONTRACT_ABI)

        print(f"从地址 {account.address} 领取代币")
        for token in TOKENS_TO_CLAIM_FROM:
            print(f"- {token}")

        gas_limit = 250000
        tx = contract.functions.claimTokens(TOKENS_TO_CLAIM_FROM).build_transaction({
            'from': account.address,
            'gas': gas_limit,
            'nonce': w3.eth.get_transaction_count(account.address),
            'chainId': CHAIN_ID
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(f"领取交易已提交: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 0:
            print("领取交易失败！")
            return False
        
        print(f"领取交易确认成功！使用Gas: {receipt.gasUsed}")
        return True
    except Exception as e:
        print(f"领取代币出错: {e}")
        return False

# 检查余额
async def check_balance(private_key: str, proxy: Optional[str]) -> str:
    try:
        w3 = create_web3_with_proxy(proxy)
        account = w3.eth.account.from_key(private_key)
        balance = w3.eth.get_balance(account.address)
        return Web3.from_wei(balance, 'ether')
    except Exception as e:
        print(f"检查余额出错: {e}")
        return '0'

# 检查代币余额
async def check_token_balances(private_key: str, proxy: Optional[str]):
    try:
        w3 = create_web3_with_proxy(proxy)
        account = w3.eth.account.from_key(private_key)
        print(f"检查账户 {account.address} 的代币余额")
        for token_address in TOKENS_TO_CLAIM_FROM:
            token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            balance = token_contract.functions.balanceOf(account.address).call()
            print(f"{token_address}: {Web3.from_wei(balance, 'ether')} 个代币")
    except Exception as e:
        print(f"检查代币余额出错: {e}")

# 处理单个账户
async def process_account(private_key: str, proxy: Optional[str], index: int, total: int, should_claim: bool, should_vote: bool, should_check_balances: bool):
    print(f"\n==================================")
    print(f"正在处理账户 {index + 1}/{total}")
    
    account = Web3().eth.account.from_key(private_key)
    balance = await check_balance(private_key, proxy)
    print(f"钱包地址: {account.address}")
    print(f"当前 ETH 余额: {balance} ETH")
    print(f"使用代理: {proxy or '无代理'}")

    if float(balance) < 0.001:
        print("警告: ETH 余额可能不足以支付Gas费")

    if should_check_balances:
        await check_token_balances(private_key, proxy)

    claim_success = False
    vote_success = False

    if should_claim:
        for attempt in range(1, 4):
            if attempt > 1:
                print(f"领取尝试 {attempt}...")
            claim_success = await claim_tokens(private_key, proxy)
            if claim_success:
                break
            if attempt < 3:
                print("等待 5 秒后重试...")
                time.sleep(5)

    if should_vote:
        for attempt in range(1, 4):
            if attempt > 1:
                print(f"投票尝试 {attempt}...")
            vote_success = await vote_on_projects(private_key, proxy)
            if vote_success:
                break
            if attempt < 3:
                print("等待 5 秒后重试...")
                time.sleep(5)

    if should_check_balances or (should_claim and claim_success) or (should_vote and vote_success):
        print("\n检查更新后的代币余额:")
        await check_token_balances(private_key, proxy)

    return {'claim_success': claim_success if should_claim else None, 'vote_success': vote_success if should_vote else None}

# 处理所有账户
async def process_accounts(should_claim: bool, should_vote: bool, should_check_balances: bool = False):
    private_keys = read_private_keys()
    proxies = read_proxies()

    if not private_keys:
        print("未找到私钥。请检查 privatekey.txt 文件。")
        return

    print(f"找到 {len(private_keys)} 个账户需要处理。")
    print(f"找到 {len(proxies)} 个代理可使用。")

    results = {'successful': {'claim': 0, 'vote': 0}, 'failed': {'claim': 0, 'vote': 0}, 'skipped': {'claim': 0, 'vote': 0}}

    for i, private_key in enumerate(private_keys):
        proxy = proxies[i % len(proxies)] if proxies else None
        result = await process_account(private_key, proxy, i, len(private_keys), should_claim, should_vote, should_check_balances)

        if should_claim:
            if result['claim_success']:
                results['successful']['claim'] += 1
            elif result['claim_success'] is False:
                results['failed']['claim'] += 1
            else:
                results['skipped']['claim'] += 1

        if should_vote:
            if result['vote_success']:
                results['successful']['vote'] += 1
            elif result['vote_success'] is False:
                results['failed']['vote'] += 1
            else:
                results['skipped']['vote'] += 1

        if i < len(private_keys) - 1:
            wait_time = 30
            print(f"等待 {wait_time} 秒后处理下一个账户...")
            time.sleep(wait_time)

    print("\n==================================")
    print("总结:")
    if should_claim:
        print(f"成功领取: {results['successful']['claim']}/{len(private_keys)}")
        print(f"领取失败: {results['failed']['claim']}/{len(private_keys)}")
    else:
        print("已跳过代币领取")
    if should_vote:
        print(f"成功投票: {results['successful']['vote']}/{len(private_keys)}")
        print(f"投票失败: {results['failed']['vote']}/{len(private_keys)}")
    else:
        print("已跳过项目投票")
    print("所有账户处理完成！")

# 定时任务
def schedule_daily(should_claim: bool, should_vote: bool, should_check_balances: bool):
    import asyncio
    print(f"机器人启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"计划任务: {'领取代币' if should_claim else ''} {'和' if should_claim and should_vote else ''} {'投票项目' if should_vote else ''}")

    asyncio.run(process_accounts(should_claim, should_vote, should_check_balances))

    while True:
        time.sleep(24 * 60 * 60)  # 每天执行一次
        print(f"执行计划任务时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        asyncio.run(process_accounts(should_claim, should_vote, should_check_balances))

# 主菜单
async def main_menu():
    while True:
        print("\n===== 开源科学自动机器人 | 空投内部人士 =====")
        print("请选择操作:")
        print("1) 从水龙头领取代币")
        print("2) 为项目投票")
        print("3) 同时领取代币和投票")
        print("4) 检查余额")
        print("5) 设置每日计划任务")
        print("6) 退出")
        choice = input("请输入您的选择 (1-6): ").strip()

        if choice == '1':
            print("\n正在运行代币领取操作...")
            await process_accounts(True, False, False)
        elif choice == '2':
            print("\n正在运行投票操作...")
            await process_accounts(False, True, False)
        elif choice == '3':
            print("\n正在运行代币领取和投票操作...")
            await process_accounts(True, True, False)
        elif choice == '4':
            print("\n正在检查余额...")
            await process_accounts(False, False, True)
        elif choice == '5':
            print("\n设置每日计划任务...")
            should_claim = input("包括代币领取？(y/n): ").lower() == 'y'
            should_vote = input("包括项目投票？(y/n): ").lower() == 'y'
            should_check_balances = input("在操作前后检查代币余额？(y/n): ").lower() == 'y'
            if not should_claim and not should_vote and not should_check_balances:
                print("您必须选择至少一个操作来安排计划任务")
                continue
            print("\n开始执行计划任务...")
            schedule_daily(should_claim, should_vote, should_check_balances)
            break
        elif choice == '6':
            print("退出程序。")
            break
        else:
            print("无效选择。请输入 1 到 6 之间的数字。")

# 主程序入口
if __name__ == "__main__":
    import asyncio
    asyncio.run(main_menu())
