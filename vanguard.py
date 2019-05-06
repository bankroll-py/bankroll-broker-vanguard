from analysis import realizedBasisForSymbol
from collections import namedtuple
from csvsectionslicer import parseSectionsForCSV, CSVSectionCriterion, CSVSectionResult
from datetime import datetime
from decimal import Decimal
from model import Activity, Bond, Cash, Currency, Instrument, Position, Stock, Trade, TradeFlags
from parsetools import lenientParse
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

import csv
import re


class PositionsAndActivity(NamedTuple):
    positions: List[Position]
    activity: List[Activity]


class VanguardPosition(NamedTuple):
    investmentName: str
    symbol: str
    shares: str
    sharePrice: str
    totalValue: str


class VanguardPositionAndActivity(NamedTuple):
    position: VanguardPosition
    activity: List[Activity]


def guessInstrumentForInvestmentName(name: str) -> Instrument:
    instrument: Instrument
    if re.match(r'^.+\s\%\s.+$', name):
        # TODO: Determine valid CUSIP for bonds
        instrument = Bond(name, currency=Currency.USD, validateSymbol=False)
    else:
        instrument = Stock(name, currency=Currency.USD)

    return instrument


def parseVanguardPositionAndActivity(vpb: VanguardPositionAndActivity
                                     ) -> Position:
    return parseVanguardPosition(vpb.position, vpb.activity)


def parseVanguardPosition(p: VanguardPosition,
                          activity: List[Activity]) -> Position:
    instrument: Instrument
    if len(p.symbol) > 0:
        instrument = Stock(p.symbol, currency=Currency.USD)
    else:
        instrument = guessInstrumentForInvestmentName(p.investmentName)

    qty = Decimal(p.shares)

    realizedBasis = realizedBasisForSymbol(instrument.symbol, activity)
    assert realizedBasis, ("Invalid realizedBasis: %s for %s" %
                           (realizedBasis, instrument))

    return Position(instrument=instrument,
                    quantity=qty,
                    costBasis=realizedBasis)


def __parsePositions(path: Path,
                     activity: List[Activity],
                     lenient: bool = False) -> List[Position]:
    with open(path, newline='') as csvfile:
        criterion = CSVSectionCriterion(
            startSectionRowMatch=["Account Number"],
            endSectionRowMatch=[],
            rowFilter=lambda r: r[1:6])
        sections = parseSectionsForCSV(csvfile, [criterion])

        if len(sections) == 0:
            return []

        vanPositions = (VanguardPosition._make(r) for r in sections[0].rows)
        vanPosAndBases = list(
            map(lambda pos: VanguardPositionAndActivity(pos, activity),
                vanPositions))

        return list(
            lenientParse(vanPosAndBases,
                         transform=parseVanguardPositionAndActivity,
                         lenient=lenient))


def parsePositionsAndActivity(path: Path,
                              lenient: bool = False) -> PositionsAndActivity:
    activity = __parseTransactions(path, lenient=lenient)
    positions = __parsePositions(path, activity=activity, lenient=lenient)
    return PositionsAndActivity(positions, activity)


class VanguardTransaction(NamedTuple):
    tradeDate: str
    settlementDate: str
    transactionType: str
    transactionDescription: str
    investmentName: str
    symbol: str
    shares: str
    sharePrice: str
    principalAmount: str
    commissionFees: str
    netAmount: str
    accruedInterest: str
    accountType: str


def forceParseVanguardTransaction(t: VanguardTransaction,
                                  flags: TradeFlags) -> Optional[Trade]:
    instrument: Instrument
    if len(t.symbol) > 0:
        instrument = Stock(t.symbol, currency=Currency.USD)
    else:
        instrument = guessInstrumentForInvestmentName(t.investmentName)

    totalFees = Decimal(t.commissionFees)
    amount = Decimal(t.principalAmount)

    if t.transactionDescription == 'Redemption':
        shares = Decimal(t.shares) * (-1)
    else:
        shares = Decimal(t.shares)

    return Trade(date=datetime.strptime(t.tradeDate, '%m/%d/%Y'),
                 instrument=instrument,
                 quantity=shares,
                 amount=Cash(currency=Currency(Currency.USD), quantity=amount),
                 fees=Cash(currency=Currency(Currency.USD),
                           quantity=totalFees),
                 flags=flags)


def parseVanguardTransaction(t: VanguardTransaction) -> Optional[Trade]:
    validTransactionTypes = set([
        'Buy', 'Sell', 'Reinvestment', 'Corp Action (Redemption)',
        'Transfer (outgoing)'
    ])

    if t.transactionType not in validTransactionTypes:
        return None

    flagsByTransactionType = {
        'Buy': TradeFlags.OPEN,
        'Sell': TradeFlags.CLOSE,
        'Reinvestment': TradeFlags.OPEN | TradeFlags.DRIP,
        'Corp Action (Redemption)': TradeFlags.CLOSE,
        'Transfer (outgoing)': TradeFlags.CLOSE,
    }

    return forceParseVanguardTransaction(
        t, flags=flagsByTransactionType[t.transactionType])


# Transactions will be ordered from newest to oldest
def __parseTransactions(path: Path, lenient: bool = False) -> List[Activity]:
    with open(path, newline='') as csvfile:
        transactionsCriterion = CSVSectionCriterion(
            startSectionRowMatch=["Account Number", "Trade Date"],
            endSectionRowMatch=[],
            rowFilter=lambda r: r[1:-1])

        sections = parseSectionsForCSV(csvfile, [transactionsCriterion])

        if len(sections) == 0:
            return []

        return list(
            filter(
                None,
                lenientParse(
                    (VanguardTransaction._make(r) for r in sections[0].rows),
                    transform=parseVanguardTransaction,
                    lenient=lenient)))
