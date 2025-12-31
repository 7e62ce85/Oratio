"""
BCH Price Service
Fetches current BCH/USD price and calculates BCH amount for USD values
"""
import requests
import time
from config import logger

# Cache for price data
price_cache = {
    "price": None,
    "timestamp": 0,
    "cache_duration": 300,  # 5 minutes
    "source": None  # Track which API provided the price
}

def get_bch_usd_price():
    """
    Fetch current BCH/USD price from multiple APIs with fallbacks
    Returns: dict with price and source, or None on error
    """
    try:
        # Check cache first
        now = time.time()
        if price_cache["price"] and (now - price_cache["timestamp"]) < price_cache["cache_duration"]:
            logger.info(f"Using cached BCH price: ${price_cache['price']} (source: {price_cache['source']})")
            return {
                "price": price_cache["price"],
                "source": price_cache["source"]
            }
        
        # Try multiple APIs in order of preference
        apis = [
            {
                "name": "Coinbase",
                "url": "https://api.coinbase.com/v2/exchange-rates?currency=BCH",
                "parser": lambda r: float(r.json()["data"]["rates"]["USD"]),
                "timeout": 5
            },
            {
                "name": "Blockchain.com",
                "url": "https://api.blockchain.com/v3/exchange/tickers/BCH-USD",
                "parser": lambda r: float(r.json()["last_trade_price"]),
                "timeout": 5
            },
            {
                "name": "CoinGecko",
                "url": "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin-cash&vs_currencies=usd",
                "parser": lambda r: float(r.json()["bitcoin-cash"]["usd"]),
                "timeout": 10
            }
        ]
        
        for api in apis:
            try:
                logger.info(f"Trying to fetch BCH price from {api['name']}...")
                response = requests.get(api["url"], timeout=api["timeout"])
                
                if response.status_code == 200:
                    price = api["parser"](response)
                    
                    if price and price > 0:
                        # Update cache
                        price_cache["price"] = price
                        price_cache["source"] = api["name"]
                        price_cache["timestamp"] = now
                        logger.info(f"Fetched BCH price from {api['name']}: ${price}")
                        return {
                            "price": price,
                            "source": api["name"]
                        }
                else:
                    logger.warning(f"{api['name']} returned status {response.status_code}")
            except Exception as e:
                logger.warning(f"Failed to fetch from {api['name']}: {str(e)}")
                continue
        
        # All APIs failed - use cached price if available
        if price_cache["price"]:
            logger.warning(f"All APIs failed, using stale cached price: ${price_cache['price']}")
            return {
                "price": price_cache["price"],
                "source": price_cache["source"] + " (cached)"
            }
        
        # Ultimate fallback: use a default price (last known stable price)
        default_price = 480.0
        logger.warning(f"All APIs failed and no cache, using default fallback price: ${default_price}")
        price_cache["price"] = default_price
        price_cache["source"] = "Default Fallback"
        return {
            "price": default_price,
            "source": "Default Fallback"
        }
        
    except Exception as e:
        logger.error(f"Unexpected error in get_bch_usd_price: {str(e)}")
        # Return cached or default price
        if price_cache["price"]:
            return {
                "price": price_cache["price"],
                "source": price_cache["source"] or "Unknown"
            }
        return {
            "price": 480.0,
            "source": "Default Fallback"
        }

def calculate_bch_amount(usd_amount):
    """
    Calculate BCH amount for given USD value
    Args:
        usd_amount: Amount in USD (e.g., 5.0)
    Returns: 
        dict with 'bch_amount', 'usd_amount', 'price_per_bch', 'source'
        or None on error
    """
    try:
        price_data = get_bch_usd_price()
        
        if not price_data or not price_data.get("price") or price_data["price"] <= 0:
            logger.error("Invalid BCH price, cannot calculate amount")
            return None
        
        price = price_data["price"]
        source = price_data.get("source", "Unknown")
        bch_amount = usd_amount / price
        
        result = {
            "bch_amount": round(bch_amount, 8),  # BCH has 8 decimal places
            "usd_amount": usd_amount,
            "price_per_bch": price,
            "price_source": source,
            "timestamp": int(time.time())
        }
        
        logger.info(f"Calculated: ${usd_amount} = {bch_amount:.8f} BCH (1 BCH = ${price} from {source})")
        return result
        
    except Exception as e:
        logger.error(f"Error calculating BCH amount: {str(e)}")
        return None

def get_membership_price():
    """
    Get current price for annual membership (5 USD in BCH)
    Returns: dict with BCH amount and USD price
    """
    # MEMBERSHIP_USD_PRICE = 5.00  # ORIGINAL - restore after testing
    MEMBERSHIP_USD_PRICE = 5.00
    
    result = calculate_bch_amount(MEMBERSHIP_USD_PRICE)
    
    if result:
        result["membership_type"] = "annual"
        result["duration_days"] = 365
        
    return result

def clear_price_cache():
    """Clear the price cache (for testing or manual refresh)"""
    price_cache["price"] = None
    price_cache["timestamp"] = 0
    logger.info("Price cache cleared")
