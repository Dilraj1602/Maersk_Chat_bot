from typing import Dict, Any
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

def create_visualization(data: pd.DataFrame, viz_type: str = None, **kwargs) -> go.Figure:
    """
    Create a visualization based on the data and specified type.
    
    Args:
        data: pandas DataFrame containing the data
        viz_type: type of visualization ('bar', 'line', 'scatter', 'table')
        **kwargs: additional arguments for the visualization
        
    Returns:
        Plotly figure object
    """
    if viz_type is None:
        # Auto-detect best visualization type based on data
        if len(data.columns) == 2:
            if data.dtypes[1].kind in 'iufc':  # numeric
                return px.bar(data, x=data.columns[0], y=data.columns[1])
            return px.pie(data, values=data.columns[1], names=data.columns[0])
        return go.Figure(data=[go.Table(
            header=dict(values=list(data.columns)),
            cells=dict(values=[data[col] for col in data.columns])
        )])
    
    viz_funcs = {
        'bar': px.bar,
        'line': px.line,
        'scatter': px.scatter,
        'pie': px.pie,
        'table': lambda data, **kwargs: go.Figure(data=[go.Table(
            header=dict(values=list(data.columns)),
            cells=dict(values=[data[col] for col in data.columns])
        )])
    }
    
    if viz_type not in viz_funcs:
        raise ValueError(f"Unsupported visualization type: {viz_type}")
    
    return viz_funcs[viz_type](data, **kwargs)

def format_currency(value: float) -> str:
    """Format value as Brazilian Real (R$)."""
    return f"R$ {value:,.2f}"

def format_date(date_str: str) -> str:
    """Format date string to dd/mm/yyyy format."""
    return pd.to_datetime(date_str).strftime('%d/%m/%Y')