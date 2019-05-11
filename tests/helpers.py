from datetime import date, datetime
from decimal import Decimal
from hypothesis.strategies import builds, dates, datetimes, decimals, from_regex, from_type, just, lists, integers, none, one_of, register_type_strategy, sampled_from, text, SearchStrategy
from bankroll import Activity, Cash, Currency, Instrument, Stock, Bond, Option, OptionType, FutureOption, Future, Forex, Position, DividendPayment, Trade, TradeFlags, Quote
from bankroll.configuration import Settings
from typing import List, Optional, TypeVar

T = TypeVar('T')


def optionals(inner: SearchStrategy[T]) -> SearchStrategy[Optional[T]]:
    return one_of(inner, none())


def cashAmounts(min_value: Decimal = Decimal('-1000000000'),
                max_value: Decimal = Decimal('1000000000')
                ) -> SearchStrategy[Decimal]:
    return decimals(allow_nan=False,
                    allow_infinity=False,
                    min_value=min_value,
                    max_value=max_value).map(Cash.quantize)


def positionQuantities(min_value: Decimal = Decimal('-1000000000'),
                       max_value: Decimal = Decimal('1000000000'),
                       allow_zero: bool = False) -> SearchStrategy[Decimal]:
    s = decimals(allow_nan=False,
                 allow_infinity=False,
                 min_value=min_value,
                 max_value=max_value).map(Position.quantizeQuantity)

    if not allow_zero:
        s = s.filter(lambda x: x != 0)

    return s


def multipliers(min_value: Decimal = Decimal('1'),
                max_value: Decimal = Decimal('10000')
                ) -> SearchStrategy[Decimal]:
    return decimals(allow_nan=False,
                    allow_infinity=False,
                    min_value=min_value,
                    max_value=max_value).map(Instrument.quantizeMultiplier)


def strikes(min_value: Decimal = Decimal('1'),
            max_value: Decimal = Decimal('100000')) -> SearchStrategy[Decimal]:
    return decimals(allow_nan=False,
                    allow_infinity=False,
                    min_value=min_value,
                    max_value=max_value).map(Option.quantizeStrike)


def cash(currency: SearchStrategy[Currency] = from_type(Currency),
         quantity: SearchStrategy[Decimal] = cashAmounts()
         ) -> SearchStrategy[Cash]:
    return builds(Cash, currency=currency, quantity=quantity)


def bonds(symbol: SearchStrategy[str] = from_regex(Bond.regexCUSIP),
          currency: SearchStrategy[Currency] = from_type(Currency)
          ) -> SearchStrategy[Bond]:
    return builds(Bond, symbol=symbol, currency=currency)


def stocks(symbol: SearchStrategy[str] = text(min_size=1),
           currency: SearchStrategy[Currency] = from_type(Currency)
           ) -> SearchStrategy[Stock]:
    return builds(Stock, symbol=symbol, currency=currency)


def options(underlying: SearchStrategy[str] = text(min_size=1),
            currency: SearchStrategy[Currency] = from_type(Currency),
            optionType: SearchStrategy[OptionType] = from_type(OptionType),
            expiration: SearchStrategy[date] = dates(),
            strike: SearchStrategy[Decimal] = strikes(),
            multiplier: SearchStrategy[Decimal] = multipliers()
            ) -> SearchStrategy[Option]:
    return builds(Option,
                  underlying=underlying,
                  currency=currency,
                  optionType=optionType,
                  expiration=expiration,
                  strike=strike,
                  multiplier=multiplier)


def futuresOptions(
        symbol: SearchStrategy[str] = text(min_size=1),
        underlying: SearchStrategy[str] = text(min_size=1),
        currency: SearchStrategy[Currency] = from_type(Currency),
        optionType: SearchStrategy[OptionType] = from_type(OptionType),
        expiration: SearchStrategy[date] = dates(),
        strike: SearchStrategy[Decimal] = strikes(),
        multiplier: SearchStrategy[Decimal] = multipliers()
) -> SearchStrategy[FutureOption]:
    return builds(FutureOption,
                  symbol=symbol,
                  underlying=underlying,
                  currency=currency,
                  optionType=optionType,
                  expiration=expiration,
                  strike=strike,
                  multiplier=multiplier)


def futures(symbol: SearchStrategy[str] = text(min_size=1),
            currency: SearchStrategy[Currency] = from_type(Currency),
            multiplier: SearchStrategy[Decimal] = multipliers()
            ) -> SearchStrategy[Future]:
    return builds(Future,
                  symbol=symbol,
                  currency=currency,
                  multiplier=multiplier)


def forex(baseCurrency: SearchStrategy[Currency] = from_type(Currency),
          quoteCurrency: SearchStrategy[Currency] = from_type(Currency)
          ) -> SearchStrategy[Forex]:
    return builds(Forex,
                  baseCurrency=baseCurrency,
                  quoteCurrency=quoteCurrency)


def instruments(currency: SearchStrategy[Currency] = from_type(Currency)
                ) -> SearchStrategy[Instrument]:
    return one_of(
        bonds(currency=currency), stocks(currency=currency),
        options(currency=currency), futuresOptions(currency=currency),
        futures(currency=currency),
        currency.flatmap(lambda cur: forex(baseCurrency=from_type(Currency).
                                           filter(lambda cur2: cur2 != cur),
                                           quoteCurrency=just(cur))))


def positions(instrument: SearchStrategy[Instrument] = instruments(),
              quantity: SearchStrategy[Decimal] = positionQuantities(),
              costBasis: SearchStrategy[Cash] = cash()
              ) -> SearchStrategy[Position]:
    return builds(Position,
                  instrument=instrument,
                  quantity=quantity,
                  costBasis=costBasis)


def dividendPayments(date: SearchStrategy[datetime] = datetimes(),
                     stock: SearchStrategy[Stock] = stocks(),
                     proceeds: SearchStrategy[Cash] = cash()
                     ) -> SearchStrategy[DividendPayment]:
    return builds(DividendPayment, date=date, stock=stock, proceeds=proceeds)


def trades(date: SearchStrategy[datetime] = datetimes(),
           instrument: SearchStrategy[Instrument] = instruments(),
           quantity: SearchStrategy[Decimal] = positionQuantities(),
           amount: SearchStrategy[Cash] = cash(),
           fees: SearchStrategy[Cash] = cash(quantity=cashAmounts(
               min_value=Decimal('0'))),
           flags: SearchStrategy[TradeFlags] = from_type(TradeFlags)
           ) -> SearchStrategy[Trade]:
    return builds(Trade,
                  date=date,
                  instrument=instrument,
                  quantity=quantity,
                  amount=amount,
                  fees=fees,
                  flags=flags)


def activity(date: SearchStrategy[datetime] = datetimes()
             ) -> SearchStrategy[Activity]:
    return one_of(dividendPayments(date=date), trades(date=date))


def quotes(bid: SearchStrategy[Optional[Cash]] = optionals(cash()),
           ask: SearchStrategy[Optional[Cash]] = optionals(cash()),
           last: SearchStrategy[Optional[Cash]] = optionals(cash()),
           close: SearchStrategy[Optional[Cash]] = optionals(cash()),
           grow_ask: bool = True) -> SearchStrategy[Quote]:
    return bid.flatmap(lambda x: builds(Quote,
                                        bid=just(x),
                                        ask=ask.map(lambda y: x + abs(y)
                                                    if x and y else y)
                                        if grow_ask else ask,
                                        last=last,
                                        close=close))


def uniformCurrencyQuotes(
        currency: SearchStrategy[Currency] = from_type(Currency),
        bid: SearchStrategy[Optional[Decimal]] = optionals(cashAmounts()),
        ask: SearchStrategy[Optional[Decimal]] = optionals(cashAmounts()),
        last: SearchStrategy[Optional[Decimal]] = optionals(cashAmounts()),
        close: SearchStrategy[Optional[Decimal]] = optionals(cashAmounts()),
        grow_ask: bool = True) -> SearchStrategy[Quote]:
    return currency.flatmap(lambda cur: quotes(
        bid=bid.map(lambda x: Cash(currency=cur, quantity=x) if x else None),
        ask=ask.map(lambda x: Cash(currency=cur, quantity=x) if x else None),
        last=last.map(lambda x: Cash(currency=cur, quantity=x) if x else None),
        close=close.map(lambda x: Cash(currency=cur, quantity=x)
                        if x else None),
        grow_ask=grow_ask))


register_type_strategy(Cash, cash())
register_type_strategy(Bond, bonds())
register_type_strategy(Stock, stocks())
register_type_strategy(Option, options())
register_type_strategy(FutureOption, futuresOptions())
register_type_strategy(Future, futures())

register_type_strategy(
    Forex,
    lists(from_type(Currency), min_size=2, max_size=2,
          unique=True).flatmap(lambda cx: forex(baseCurrency=just(cx[0]),
                                                quoteCurrency=just(cx[1]))))

register_type_strategy(Instrument, instruments())

register_type_strategy(
    Position,
    from_type(Instrument).flatmap(lambda i: positions(
        instrument=just(i), costBasis=cash(currency=just(i.currency)))))

register_type_strategy(Activity, activity())
register_type_strategy(DividendPayment, dividendPayments())

register_type_strategy(
    TradeFlags,
    sampled_from([
        TradeFlags.OPEN, TradeFlags.CLOSE, TradeFlags.OPEN | TradeFlags.DRIP,
        TradeFlags.OPEN | TradeFlags.ASSIGNED_OR_EXERCISED,
        TradeFlags.CLOSE | TradeFlags.EXPIRED,
        TradeFlags.CLOSE | TradeFlags.ASSIGNED_OR_EXERCISED
    ]))

register_type_strategy(
    Trade,
    from_type(Instrument).flatmap(lambda i: trades(
        instrument=just(i),
        amount=cash(currency=just(i.currency)),
        fees=cash(currency=just(i.currency),
                  quantity=cashAmounts(min_value=Decimal('0'))))))

register_type_strategy(Quote, uniformCurrencyQuotes())

register_type_strategy(
    Settings, one_of([from_type(s) for s in Settings.__subclasses__()]))


def cashUSD(amount: Decimal) -> Cash:
    return Cash(currency=Currency.USD, quantity=amount)


def splitAndStripCSVString(s: str) -> List[str]:
    return list(elem.strip() for elem in s.split(","))
