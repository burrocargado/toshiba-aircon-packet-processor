import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (Column, Integer, String,
    DateTime, Text, BLOB)

class BaseEngine(object):
    def __init__(self, url):
        self.engine = create_engine(url, encoding="utf-8")

class BaseSession(BaseEngine):
    def __init__(self, url):
        super().__init__(url)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

Base = declarative_base()

class Packet(Base):
    __tablename__ = 'packet'

    id = Column('id', Integer, primary_key=True)
    time = Column(DateTime)
    stat = Column(String(2))
    txaddr = Column(String(2))
    rxaddr = Column(String(2))
    opc1 = Column(String(2))
    mode = Column(String(2))
    opc2 = Column(String(2))
    payload = Column(Text)
    rawdata = Column(BLOB)

class Status(Base):
    __tablename__ = 'status'

    id = Column('id', Integer, primary_key=True)
    time = Column(DateTime)
    power = Column(String(3))
    mode = Column(String(9))
    clean = Column(String(3))
    fanlv = Column(String(4))
    settmp = Column(Integer)
    temp = Column(Integer)
    pwrlv1 = Column(Integer)
    pwrlv2 = Column(Integer)
    sens_ta = Column(Integer)
    sens_tcj = Column(Integer)
    sens_tc = Column(Integer)
    sens_te = Column(Integer)
    sens_to = Column(Integer)
    sens_td = Column(Integer)
    sens_ts = Column(Integer)
    sens_ths = Column(Integer)
    sens_current = Column(Integer)
    filter_time = Column(Integer)
    filter = Column(String(3))
    vent = Column(String(3))
    humid = Column(String(3))


class DB():

    def __init__(self):
        url = 'sqlite:///packetlog/log.sqlite3'
        Base.metadata.create_all(bind=BaseEngine(url).engine)
        self.session = BaseSession(url).session

    def write_packet(self, stat, packet=None):
        p = Packet()
        p.stat = stat
        p.time = dt.datetime.now()
        if packet is not None:
            p.txaddr = bytes([packet[0]]).hex()
            p.rxaddr = bytes([packet[1]]).hex()
            p.opc1 = bytes([packet[2]]).hex()
            p.mode = bytes([packet[4]]).hex()
            p.opc2 = bytes([packet[5]]).hex()
            p.payload = bytes(packet[6:-1]).hex()
            p.rawdata = bytes(packet)
        self.session.add(p)
        self.session.commit()

        return p.id

    def write_status(self, status):
        s = Status(**status)
        s.time = dt.datetime.now()
        self.session.add(s)
        self.session.commit()
