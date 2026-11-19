"""Isolate another native service without sharing queues, groups or credentials."""
from contextlib import contextmanager
from backend import copy_trading


class NamespacedStore:
    def __init__(self,namespace):self.namespace=namespace
    def kind(self,value):
        return self.namespace+value[5:] if isinstance(value,str) and value.startswith('ninja_') else value
    def get(self,kind,key):return copy_trading.get(self.kind(kind),key)
    def put(self,kind,key,value):return copy_trading.put(self.kind(kind),key,value)
    def listing(self,kind):return copy_trading.listing(self.kind(kind))
    def __getattr__(self,key):return getattr(copy_trading,key)
    @contextmanager
    def connect(self):
        owner=self
        class Connection:
            def __init__(self,db):self.db=db
            def execute(self,sql,parameters=()):
                return self.db.execute(sql.replace('ninja_',owner.namespace+'_'),tuple(owner.kind(p) for p in parameters))
        with copy_trading.connect() as db:yield Connection(db)
