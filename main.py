from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Annotated
import models
import datetime
from database import engine, SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import date
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler

app = FastAPI()
models.Base.metadata.create_all(bind=engine)


class PriceBase(BaseModel):
    price: int
    date: date

class CoinBase(BaseModel):
    coin_name: str
    prices: List[PriceBase]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]


scheduler = AsyncIOScheduler()

def update_prices():
    print("update_prices job started")
    db = SessionLocal()
    try:
        #pripajanie na coingecko pro ziskani aktualni ceny
        coins = db.query(models.Coins).all()
        headers = {
            "accept": "application/json",
            "x-cg-demo-api-key": "CG-AQSweWoj5RghwcuGRhgoaoKa"
        }
        for coin in coins:
            url = f"https://api.coingecko.com/api/v3/coins/{coin.coin_name}"
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                continue

            data = response.json()

            new_price = data.get("market_data", {}).get("current_price", {}).get("usd")
            if new_price is None:
                continue

           #podme cheknut jestli v databaze mame coin z tabulky coins s dnesnym datumem, pokud jo, aktualizujeme cenu kazdou minutu
            price_record = db.query(models.Prices).filter(
                models.Prices.coin_id == coin.id,
                models.Prices.date == date.today()
            ).first()

            if price_record:

                price_record.price = new_price
            else:

                new_price_record = models.Prices(
                    price=new_price,
                    date=date.today(),
                    coin_id=coin.id
                )
                db.add(new_price_record)
                try:
                    db.commit()
                except IntegrityError as e:
                    print(f"IntegrityError for {coin.coin_name}: {e}")
                    db.rollback()
                    # Optionally, try fetching and updating the existing record here
        db.commit()

        print("Prices updated successfully")
    except Exception as e:
        print(f"Error updating prices: {e}")
        db.rollback()
    finally:
        db.close()



scheduler.add_job(update_prices, 'interval', minutes=1)


@app.on_event("startup")
async def start_scheduler():
    print("Starting scheduler")
    scheduler.start()



@app.get("/coins/{coin_name}/{date}")
async def read_coin_price(coin_name: str, date: date, db: Session = Depends(get_db)):

    coin = db.query(models.Coins).filter(models.Coins.coin_name == coin_name).first()
    if not coin:
        raise HTTPException(status_code=404, detail="Coin not found")


    price_record = db.query(models.Prices).filter(
        models.Prices.coin_id == coin.id,
        models.Prices.date == date
    ).first()

    if not price_record:
        raise HTTPException(status_code=404, detail="Price not found for the given coin and date")

    return price_record


@app.post("/coins/")
async def create_coins(coin: CoinBase, db: db_dependency):

    # pripajanie na ciongecko - check jestli dany coin existuje
    url = f"https://api.coingecko.com/api/v3/coins/{coin.coin_name}"
    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": "CG-AQSweWoj5RghwcuGRhgoaoKa"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 404:
        return {"message": "Coin does not exist"}

    existing_coin = db.query(models.Coins).filter(models.Coins.coin_name == coin.coin_name).first()
    if existing_coin:
        db_coin = existing_coin
    else:
        db_coin = models.Coins(coin_name=coin.coin_name)
        db.add(db_coin)
        db.commit()
        db.refresh(db_coin)


    for price in coin.prices:

        existing_price = db.query(models.Prices).filter(
            models.Prices.coin_id == db_coin.id,
            models.Prices.date == price.date
        ).first()

        if existing_price:
            # pokud cena pre coin a date existuje -- update
            existing_price.price = price.price
        else:
            # pokud neexistuje -- create
            db_price = models.Prices(
                price=price.price,
                date=price.date,
                coin_id=db_coin.id
            )
            db.add(db_price)

    db.commit()
    return {"message": "Coins and prices added successfully"}


@app.delete("/coins/{coin_name}/{price_date}")
async def delete_coin_price(coin_name: str, price_date: date, db: Session = Depends(get_db)):
    #najdi coin podla mena
    coin = db.query(models.Coins).filter(models.Coins.coin_name == coin_name).first()
    if not coin:
        raise HTTPException(status_code=404, detail="Coin not found")


    price_record = db.query(models.Prices).filter(
        models.Prices.coin_id == coin.id,
        models.Prices.date == price_date
    ).first()

    if not price_record:
        raise HTTPException(status_code=404, detail="Price record not found for the given coin and date")


    db.delete(price_record)
    db.commit()
    return {"message": "Price record deleted successfully"}



