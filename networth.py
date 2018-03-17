import imaplib, json, requests, sys, collections, sqlite3

from config import *
from datetime import datetime, timedelta
from multiprocessing.dummy import Pool

CAPITALONE_SUBJECT = "Your requested balance summary"
BOFA_SUBJECT =  "Your Available Balance"
DB_FILE = "stocks.sql"

def initDb():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name="stock"')
    if len(c.fetchall()) == 0:
        c.execute('CREATE TABLE stock(ticker, insertDate, currVal, openPrice)')
    conn.commit()
    conn.close()

def insertStock(ticker,currVal,openPrice):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        qry = 'UPDATE stock SET insertDate = DATE("now", "localtime"), currVal = {}, openPrice = {} WHERE ticker="{}"'
        c.execute(qry)
    except Exception:
        qry = 'INSERT INTO stock (ticker, insertDate, currVal, openPrice) VALUES ("{}",DATE("now", "localtime"),{},{})'.format(ticker, currVal, openPrice)
        c.execute(qry)
    conn.commit()
    conn.close()

def getCachedStock(ticker):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    qry = 'SELECT * FROM stock WHERE ticker = "{}"'.format(ticker)
    c.execute(qry)
    stocks = c.fetchall()
    price = collections.namedtuple('price','ticker insertDate currVal openPrice')
    return price(*stocks[0])


#Bank of America accounts
def getBofA(mail):
    assets = {}
    mail.select("inbox") # connect to inbox.
    result, data = mail.uid('search', '(HEADER Subject "'+BOFA_SUBJECT+'")' ) # search and return uids instead
    uids = data[0].split()
    for uid in uids[::-1]:
        result, data = mail.uid('fetch', uid, '(RFC822)')
        raw_email = str(data[0][1])

        if "Balance: $" in raw_email:
            #find balance
            start = raw_email.find("Balance: $") + 10
            end = raw_email[start:].find("\\r")+start
            balance = float(raw_email[start:end].replace(',',''))
            #find account
            start = raw_email.find("Account: ")+9
            end = raw_email[start:].find("\\r")+start
            account = raw_email[start:end]

            if account not in assets.keys():
                assets[account] = balance
        if len(assets.keys()) == 2:
            break
    return assets

#Capital One balance
def getCapitalOne(mail):
    assets = {}
    mail.select("inbox") # connect to inbox.
    result, data = mail.uid('search', '(HEADER Subject "'+CAPITALONE_SUBJECT+'")' ) # search and return uids instead
    uid = data[0].split()[-1]
    result, data = mail.uid('fetch', uid, '(RFC822)')
    raw_email = str(data[0][1])
    if "balance is $" in raw_email:
        #find balance
        start = raw_email.find("balance is $") + 12
        end = raw_email[start:].find(".")+start+2
        balance = float(raw_email[start:end].replace(',',''))
        assets["CapitalOne"] = -1*balance
    return assets

def dailyTotal(stock):
    ticker = stock["1. symbol"]
    openPrice = getOpenPrice(ticker)
    currPrice = float(stock["2. price"])
    insertStock(ticker,currPrice,openPrice)
    return (currPrice * STOCKS[ticker], (currPrice - openPrice) * STOCKS[ticker])

def getOpenPrice(ticker):
    detailsUrl = "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={0}&apikey={1}".format(ticker,STOCK_API_KEY)
    response = requests.get(detailsUrl)
    data = json.loads(response.content)
    return float(data["Time Series (Daily)"][lastClose()]["4. close"])

def dailyPercent(ticker):
    url = "https://www.alphavantage.co/query?function=BATCH_STOCK_QUOTES&symbols={0}&apikey={1}".format(ticker,STOCK_API_KEY)
    response = requests.get(url)
    result = json.loads(response.content)
    currPrice = float(result["Stock Quotes"][0]["2. price"])
    openPrice = getOpenPrice(ticker)
    insertStock(ticker,currPrice,openPrice)
    return round(100*(currPrice - openPrice)/openPrice,2)

#stocks
def liveStockAssets():
    url = "https://www.alphavantage.co/query?function=BATCH_STOCK_QUOTES&symbols={0}&apikey={1}".format(",".join(STOCKS.keys()),STOCK_API_KEY)
    response = requests.get(url)
    prices = json.loads(response.content)
    results = prices["Stock Quotes"]
    '''assets = [(stock["1. symbol"],float(stock["2. price"])*STOCKS[stock["1. symbol"]]) for stock in results]
    balance = sum([asset[1] for asset in assets])'''
    threadPool = Pool(5)
    dailyTotals = threadPool.map(dailyTotal,results)
    threadPool.close()
    threadPool.join()
    balance = int(sum([dt[0] for dt in dailyTotals]))
    totalDayChange = int(sum([dt[1] for dt in dailyTotals]))
    Result = collections.namedtuple("Result",["balance","dayChange"])
    return Result(balance,totalDayChange)

def cachedStockAssets():
    prices = [getCachedStock(ticker) for ticker in STOCKS.keys()]
    totalOpen = int(sum([price.openPrice*STOCKS[price.ticker] for price in prices]))
    totalCurrent = int(sum([price.currVal*STOCKS[price.ticker] for price in prices]))
    Result = collections.namedtuple("Result",["balance","dayChange"])
    return Result(totalCurrent,totalCurrent - totalOpen)


def lastClose():
    today = datetime.today()
    if today.weekday == 6 or today.weekday == 1:
        #find last friday
        lastClose = today - timedelta(2 if today.weekday==7 else 3)
    else:
        lastClose = today - timedelta(1)
    return lastClose.strftime('%Y-%m-%d')

if sys.argv[1] == "init":
    initDb()

elif sys.argv[1] == "net":
    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(EMAIL_USERNAME, EMAIL_PASSWORD)
    mail.list()
    # Out: list of "folders" aka labels in gmail.
    mail.select("inbox") # connect to inbox.
    bofaAssets = getBofA(mail)
    capitalOneAssets = getCapitalOne(mail)
    totalAssets = {**bofaAssets, **capitalOneAssets, **ASSETS}
    totalAssets["Stocks"] = liveStockAssets().balance

    print(datetime.today())
    for (account,balance) in totalAssets.items():
        print(str(balance)+" in "+account)
    print("Total: "+str(round(sum(totalAssets.values()),2)))

elif sys.argv[1] == "daily":
    try:
        stockAssets = liveStockAssets()
    except Exception:
        stockAssets = cachedStockAssets()
    if stockAssets.dayChange < 0:
        print("-$"+str(-1 * stockAssets.dayChange))
    else:
        print("$"+str(stockAssets.dayChange))

elif sys.argv[1] == "ticker":
    ticker = sys.argv[2]
    try:
        change = dailyPercent(ticker)
    except Exception:
        cachedData = getCachedStock(ticker)
        change = round(100*(cachedData[2] - cachedData[3])/cachedData[3],2)
    print(str(change)+"% "+ticker)

