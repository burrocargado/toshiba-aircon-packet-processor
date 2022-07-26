from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (Column, Integer, String, Float, 
    DateTime, Date, Text, ForeignKey, BLOB)
from sqlalchemy import func
from sqlalchemy.orm import relationship, backref

import datetime as dt

class BaseEngine(object):
    def __init__(self, url):
        self.engine = create_engine(url, encoding="utf-8")#, echo=True)

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

class DB():
    
    def __init__(self, url='sqlite:///db.sqlite3'):
        Base.metadata.create_all(bind=BaseEngine(url).engine)
        self.session = BaseSession(url).session

    def write_packet(self, stat, packet=None):
        p = Packet()
        p.stat = stat
        p.time = dt.datetime.now()
        if packet is not None:
            p.txaddr = bytes(packet[0:1]).hex()
            p.rxaddr = bytes(packet[1:2]).hex()
            p.opc1 = bytes(packet[2:3]).hex()
            p.mode = bytes(packet[4:5]).hex()
            p.opc2 = bytes(packet[5:6]).hex()
            p.payload = bytes(packet[6:-1]).hex()
            p.rawdata = bytes(packet)
        self.session.add(p)
        self.session.commit()

        return p.id
