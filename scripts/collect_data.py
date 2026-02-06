"""
밈 코인 섹터 - 데이터 수집 스크립트
DexScreener API + CoinGecko API에서 밈코인 데이터를 수집합니다.
체인: Solana, Ethereum, Base
"""

import json
import time
import os
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ============================================================
# Config
# ============================================================
TARGET_CHAINS = {"solana", "ethereum", "base"}
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
KST = timezone(timedelta(hours=9))

DEX_BASE = "https://api.dexscreener.com"
CG_BASE = "https://api.coingecko.com/api/v3"

# ============================================================
# HTTP Helper
# ============================================================
def fetch_json(url, retries=3, delay=2):
    """Fetch JSON from URL with retry logic."""
    for attempt in range(retries):
        try:
            req = Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "MemeCoinsBot/1.0"
            })
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except (URLError, HTTPError, json.JSONDecodeError) as e:
            print(f"  [attempt {attempt+1}/{retries}] Error fetching {url}: {e}")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    return None


# ============================================================
# DexScreener: Top Boosted Tokens
# ============================================================
def fetch_top_boosts():
    """가장 많은 부스트를 받은 토큰 (주목도 시그널)"""
    print("📡 Fetching DexScreener top boosts...")
    data = fetch_json(f"{DEX_BASE}/token-boosts/top/v1")
    if not data:
        return []
    tokens = data if isinstance(data, list) else [data]
    # Filter by target chains
    filtered = [t for t in tokens if t.get("chainId") in TARGET_CHAINS]
    print(f"  → {len(filtered)} tokens on target chains (of {len(tokens)} total)")
    return filtered


def fetch_latest_boosts():
    """최신 부스트 토큰"""
    print("📡 Fetching DexScreener latest boosts...")
    data = fetch_json(f"{DEX_BASE}/token-boosts/latest/v1")
    if not data:
        return []
    tokens = data if isinstance(data, list) else [data]
    filtered = [t for t in tokens if t.get("chainId") in TARGET_CHAINS]
    print(f"  → {len(filtered)} tokens on target chains (of {len(tokens)} total)")
    return filtered


# ============================================================
# DexScreener: Latest Token Profiles
# ============================================================
def fetch_latest_profiles():
    """최신 등록 토큰 프로필"""
    print("📡 Fetching DexScreener latest profiles...")
    data = fetch_json(f"{DEX_BASE}/token-profiles/latest/v1")
    if not data:
        return []
    tokens = data if isinstance(data, list) else [data]
    filtered = [t for t in tokens if t.get("chainId") in TARGET_CHAINS]
    print(f"  → {len(filtered)} profiles on target chains (of {len(tokens)} total)")
    return filtered[:20]


# ============================================================
# DexScreener: Token Pair Data (price, volume, liquidity)
# ============================================================
def fetch_token_pairs(chain_id, token_address):
    """토큰의 거래 페어 데이터 (가격, 거래량, 유동성)"""
    data = fetch_json(f"{DEX_BASE}/tokens/v1/{chain_id}/{token_address}")
    if not data:
        return None
    pairs = data if isinstance(data, list) else data.get("pairs", [])
    if not pairs:
        return None
    # Sort by 24h volume and return top pair
    pairs.sort(key=lambda p: p.get("volume", {}).get("h24", 0) or 0, reverse=True)
    return pairs[0]


def enrich_with_pair_data(tokens, batch_size=5, delay=1.0):
    """
    부스트 토큰에 실시간 가격/거래량/유동성 데이터를 추가합니다.
    DexScreener rate limit: 300 req/min for token endpoints
    """
    print(f"📊 Enriching {len(tokens)} tokens with pair data...")
    enriched = []

    for i in range(0, len(tokens), batch_size):
        batch = tokens[i:i + batch_size]
        for token in batch:
            chain = token.get("chainId", "")
            addr = token.get("tokenAddress", "")
            if not chain or not addr:
                enriched.append({**token, "pairData": None})
                continue

            pair = fetch_token_pairs(chain, addr)
            if pair:
                enriched.append({
                    **token,
                    "pairData": {
                        "name": pair.get("baseToken", {}).get("name", ""),
                        "symbol": pair.get("baseToken", {}).get("symbol", ""),
                        "priceUsd": pair.get("priceUsd"),
                        "priceChange": pair.get("priceChange", {}),
                        "volume": pair.get("volume", {}),
                        "liquidity": pair.get("liquidity", {}),
                        "marketCap": pair.get("marketCap"),
                        "fdv": pair.get("fdv"),
                        "dexId": pair.get("dexId", ""),
                        "pairAddress": pair.get("pairAddress", ""),
                        "pairCreatedAt": pair.get("pairCreatedAt"),
                        "url": pair.get("url", ""),
                        "txns": pair.get("txns", {}),
                    }
                })
                print(f"  ✅ {pair.get('baseToken', {}).get('symbol', addr[:8])} - ${pair.get('priceUsd', '?')}")
            else:
                enriched.append({**token, "pairData": None})
                print(f"  ⚠️ No pair data for {addr[:12]}...")

        if i + batch_size < len(tokens):
            time.sleep(delay)

    return enriched


# ============================================================
# CoinGecko: Trending Coins
# ============================================================
def fetch_trending():
    """CoinGecko 24시간 트렌딩 코인"""
    print("📡 Fetching CoinGecko trending...")
    data = fetch_json(f"{CG_BASE}/search/trending")
    if not data:
        return []
    coins = data.get("coins", [])
    print(f"  → {len(coins)} trending coins")
    results = []
    for coin in coins:
        item = coin.get("item", {})
        results.append({
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "symbol": item.get("symbol", ""),
            "thumb": item.get("thumb", ""),
            "small": item.get("small", ""),
            "marketCapRank": item.get("market_cap_rank"),
            "priceChangePercentage24h": (
                item.get("data", {}).get("price_change_percentage_24h", {}).get("usd")
            ),
            "price": item.get("data", {}).get("price"),
            "marketCap": item.get("data", {}).get("market_cap"),
            "totalVolume": item.get("data", {}).get("total_volume"),
            "sparkline": item.get("data", {}).get("sparkline"),
        })
    return results


# ============================================================
# CoinGecko: Meme Coin Category Market Data
# ============================================================
def fetch_meme_category_coins():
    """CoinGecko 밈코인 카테고리 - 시총 순 상위 코인"""
    print("📡 Fetching CoinGecko meme category coins...")
    url = (
        f"{CG_BASE}/coins/markets?"
        "vs_currency=usd&category=meme-token&order=market_cap_desc"
        "&per_page=30&page=1&sparkline=false"
        "&price_change_percentage=1h,24h,7d"
    )
    data = fetch_json(url)
    if not data:
        return []
    print(f"  → {len(data)} meme coins by market cap")
    results = []
    for coin in data:
        results.append({
            "id": coin.get("id", ""),
            "name": coin.get("name", ""),
            "symbol": coin.get("symbol", "").upper(),
            "image": coin.get("image", ""),
            "currentPrice": coin.get("current_price"),
            "marketCap": coin.get("market_cap"),
            "marketCapRank": coin.get("market_cap_rank"),
            "totalVolume": coin.get("total_volume"),
            "priceChange1h": coin.get("price_change_percentage_1h_in_currency"),
            "priceChange24h": coin.get("price_change_percentage_24h_in_currency"),
            "priceChange7d": coin.get("price_change_percentage_7d_in_currency"),
            "ath": coin.get("ath"),
            "athChangePercentage": coin.get("ath_change_percentage"),
        })
    return results


# ============================================================
# Main
# ============================================================
def main():
    now_kst = datetime.now(KST)
    timestamp = now_kst.strftime("%Y-%m-%d %H:%M:%S KST")
    date_str = now_kst.strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"🚀 밈 코인 섹터 데이터 수집")
    print(f"📅 {timestamp}")
    print(f"🔗 체인: Solana, Ethereum, Base")
    print(f"{'='*60}\n")

    # 1. DexScreener - Top Boosted
    top_boosts_raw = fetch_top_boosts()
    # Deduplicate
    seen = set()
    top_boosts_unique = []
    for t in top_boosts_raw:
        key = f"{t.get('chainId')}:{t.get('tokenAddress')}"
        if key not in seen:
            seen.add(key)
            top_boosts_unique.append(t)
    top_boosts = enrich_with_pair_data(top_boosts_unique[:15])
    time.sleep(1)

    # 2. DexScreener - Latest Boosted
    latest_boosts_raw = fetch_latest_boosts()
    seen2 = set()
    latest_boosts_unique = []
    for t in latest_boosts_raw:
        key = f"{t.get('chainId')}:{t.get('tokenAddress')}"
        if key not in seen2:
            seen2.add(key)
            latest_boosts_unique.append(t)
    latest_boosts = enrich_with_pair_data(latest_boosts_unique[:10])
    time.sleep(1)

    # 3. DexScreener - Latest Profiles
    profiles = fetch_latest_profiles()
    time.sleep(1)

    # 4. CoinGecko - Trending
    trending = fetch_trending()
    time.sleep(1)

    # 5. CoinGecko - Meme Category
    meme_coins = fetch_meme_category_coins()

    # Assemble output
    output = {
        "meta": {
            "timestamp": timestamp,
            "date": date_str,
            "chains": list(TARGET_CHAINS),
            "sources": ["DexScreener", "CoinGecko"],
        },
        "topBoosts": top_boosts,
        "latestBoosts": latest_boosts,
        "latestProfiles": profiles,
        "trending": trending,
        "memeCoins": meme_coins,
    }

    # Save JSON
    os.makedirs(DATA_DIR, exist_ok=True)

    # Latest file (always overwritten)
    latest_path = os.path.join(DATA_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Saved: {latest_path}")

    # Daily archive
    archive_path = os.path.join(DATA_DIR, f"{date_str}.json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved: {archive_path}")

    # Summary
    print(f"\n{'='*60}")
    print(f"📊 수집 완료 요약:")
    print(f"  • 탑 부스트: {len(top_boosts)}개")
    print(f"  • 최신 부스트: {len(latest_boosts)}개")
    print(f"  • 최신 프로필: {len(profiles)}개")
    print(f"  • 트렌딩: {len(trending)}개")
    print(f"  • 밈코인 시총 TOP: {len(meme_coins)}개")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
