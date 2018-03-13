import imaplib, email, json, requests
from pprint import pprint
from config import *

CAPITALONE_SUBJECT = "Your requested balance summary"
BOFA_SUBJECT =  "Your Available Balance"


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

#stocks
def getStockAssets():
    balance = 0
    url = "https://www.alphavantage.co/query?function=BATCH_STOCK_QUOTES&symbols={0}&apikey={1}".format(",".join(STOCKS.keys()),STOCK_API_KEY,)
    response = requests.get(url)
    prices = json.loads(response.content)
    for stocks in prices["Stock Quotes"]:
        balance += float(stocks["2. price"]) * STOCKS[stocks["1. symbol"]]
    if len(prices["Stock Quotes"]) != len(STOCKS.keys()):
        print("Some stock prices not found:")
        pricesFound = set([detail["1. symbol"] for detail in prices["Stock Quotes"]])
        stocksNotFound = set(STOCKS.keys()) - pricesFound
        [print(stock+" ("+str(STOCKS[stock])+" shares)") for stock in stocksNotFound]
        print()
    return round(balance,2)


mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login(EMAIL_USERNAME, EMAIL_PASSWORD)
mail.list()
# Out: list of "folders" aka labels in gmail.
mail.select("inbox") # connect to inbox.
bofaAssets = getBofA(mail)
capitalOneAssets = getCapitalOne(mail)
totalAssets = {**bofaAssets, **capitalOneAssets, **ASSETS}
totalAssets["Stocks"] = getStockAssets()


for (account,balance) in totalAssets.items():
    print(str(balance)+" in "+account)
print()
print("Total: "+str(round(sum(totalAssets.values()),2)))
