"""Operators supported by Stratix. Not an assertion of full SQ/TN parity."""
OPERATORS={
    'GREATER_THAN':'Mayor que (>)','LESS_THAN':'Menor que (<)','EQUAL_TO':'Igual a (≈)',
    'CROSS_ABOVE':'Cruza por encima','CROSS_BELOW':'Cruza por debajo','CROSS_BOTH':'Cruza en ambos sentidos',
    'PRICE_ABOVE':'Precio por encima','PRICE_BELOW':'Precio por debajo',
    'BULLISH':'Tendencia alcista','BEARISH':'Tendencia bajista',
}
NUMERIC=set(OPERATORS)-{'PRICE_ABOVE','PRICE_BELOW','BULLISH','BEARISH'}
PRICE_INDICATORS={'EMA','SMA','DEMA','TEMA','HMA','WMA','KAMA','HIGHEST','LOWEST','PIVOT_POINTS','VWAP'}


def compatible(indicator):
    name=indicator.upper()
    if name in ('HIGHEST','LOWEST','VWAP'):
        return {'PRICE_ABOVE','PRICE_BELOW'}
    result=set(NUMERIC)
    if name in PRICE_INDICATORS: result|={'PRICE_ABOVE','PRICE_BELOW'}
    if name in ('SUPERTREND','PSAR'): result|={'BULLISH','BEARISH'}
    return result


def validate_selection(indicators,operators):
    if operators is None: return
    if not operators or set(operators)-set(OPERATORS):
        raise ValueError('Selecciona al menos un operador admitido')
    missing=[name for name in indicators if not compatible(name)&set(operators)]
    if missing: raise ValueError('Sin operador compatible para: '+', '.join(missing))
