"""RocketPass configuration, isolated from PropPass and account copier."""
from typing import Literal
from pydantic import Field,model_validator
from backend.ninja_bridge import Settings,Group,install_routes as install_native_routes


class RocketSettings(Settings):
    timeframe_minutes:Literal[5]=5
    symbol:str=Field(default='MNQ 12-26',pattern=r'^[A-Za-z0-9._ -]{1,40}$')
    lots:int=Field(default=2,ge=1,le=100)
    sl_usd:float=Field(default=2000,gt=0,le=100000)
    tp_usd:float=Field(default=1500,gt=0,le=100000)
    target:float=Field(default=3000,gt=0,le=100000)
    max_loss:float=Field(default=2000,gt=0,le=100000)
    daily_profit_limit:float=Field(default=0,ge=0,le=100000)
    daily_loss_limit:float=Field(default=0,ge=0,le=100000)
    trend_period:Literal[40]=40
    direction:Literal['AUTO','LONG','SHORT']='AUTO'
    limit_count:int=Field(default=3,ge=0,le=10)
    limit_contracts:int=Field(default=2,ge=1,le=100)
    stop_count:int=Field(default=3,ge=0,le=10)
    stop_contracts:int=Field(default=2,ge=1,le=100)
    max_contracts:int=Field(default=30,ge=1,le=100)
    grid_same_as_initial:bool=True

    @model_validator(mode='after')
    def grid_budget(self):
        initial=max([self.lots]+[v.lots for v in self.account_overrides.values() if v.lots is not None])
        if self.grid_same_as_initial:self.limit_contracts=self.stop_contracts=self.lots
        lc,sc=(initial,initial) if self.grid_same_as_initial else (self.limit_contracts,self.stop_contracts)
        if initial+self.limit_count*lc+self.stop_count*sc>self.max_contracts:
            raise ValueError('La suma de contratos iniciales, limits y stops excede el máximo total configurado')
        return self


class RocketGroup(Group):
    settings:RocketSettings


def install_routes(app):
    # Update saved templates; an applied native group still requires reapplication.
    from backend import copy_trading as store
    for group in store.listing('rocket_group'):
        group['settings'].update(timeframe_minutes=5,trend_period=40)
        store.put('rocket_group',group['id'],group)
    for queue in store.listing('rocket_queue'):
        for item in queue.get('items',[]):
            if item.get('state')=='PENDING':item['settings'].update(timeframe_minutes=5,trend_period=40)
        store.put('rocket_queue',queue['connection'],queue)
    install_native_routes(app,'rocket',RocketSettings,RocketGroup)
