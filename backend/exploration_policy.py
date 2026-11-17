"""One optional Prop Firm mode; technical indicators only for new searches."""
ACCOUNT_LIMITS=tuple(f'max_{period}_{kind}_pct' for period in ('daily','weekly','monthly','account') for kind in ('loss','gain'))


def normalize_config(config):
    value=dict(config)
    if any(str(name).upper().startswith('MACRO_') for name in value.get('enabled_indicators',[])):
        raise ValueError('Los indicadores FRED fueron retirados del motor. Selecciona indicadores técnicos.')
    value.pop('use_macro',None);value.pop('macro_series',None)
    for field in ACCOUNT_LIMITS: value[field]=0.
    if value.get('prop_firm_filter',False):
        value['max_daily_loss_pct']=float(value.get('prop_firm_daily_loss_pct',4))
        value['max_account_loss_pct']=float(value.get('prop_firm_total_dd_pct',8))
        value['max_account_gain_pct']=float(value.get('prop_firm_target_pct',8))
    elif value.get('objective')=='pass_rate':
        raise ValueError('Activa Modo Prop Firm para optimizar la aprobación del reto.')
    return value
