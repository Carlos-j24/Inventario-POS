"""Costo promedio ponderado (spec 004, decisión 1).

Funciones sin acceso a la base de datos, salvo replay_costs, que recibe las clases de modelo
para poder usarse también desde una migración (con los modelos históricos).
"""
from decimal import Decimal

COST_PLACES = Decimal("0.0001")


def next_average(qty_before, avg_before, qty_in, cost_in):
    """Costo promedio tras una entrada de qty_in unidades a cost_in.

    Si no había existencias (o estaban en negativo por ventas sin conexión), el promedio
    anterior no significa nada y el nuevo costo es el de la entrada.
    """
    qty_before, avg_before = Decimal(qty_before), Decimal(avg_before)
    qty_in, cost_in = Decimal(qty_in), Decimal(cost_in)
    if qty_before <= 0:
        return cost_in.quantize(COST_PLACES)
    total = qty_before * avg_before + qty_in * cost_in
    return (total / (qty_before + qty_in)).quantize(COST_PLACES)


def replay_costs(StockMovement, StockLevel):
    """Recalcula el costo de todos los movimientos y el promedio de cada existencia, en orden.

    Para datos anteriores a la spec 004: las entradas ya traían su costo; a las salidas (y a las
    devoluciones sin costo) se les pone el promedio de ese momento y se marcan cost_estimated.
    """
    state = {}  # (producto, bodega) -> [cantidad, promedio]
    for mov in StockMovement.objects.order_by("created_at", "pk"):
        key = (mov.product_id, mov.warehouse_id)
        qty, avg = state.get(key, [Decimal(0), Decimal(0)])
        estimated = mov.cost_estimated
        if mov.quantity > 0:
            cost = mov.unit_cost
            if cost is None:  # devolución o ajuste viejos: vuelven al promedio vigente
                cost, estimated = avg, True
            avg = next_average(qty, avg, mov.quantity, cost)
        else:
            cost = avg
            estimated = estimated or mov.unit_cost is None
        qty += mov.quantity
        state[key] = [qty, avg]
        if mov.unit_cost != cost or mov.cost_estimated != estimated:
            mov.unit_cost, mov.cost_estimated = cost, estimated
            mov.save(update_fields=["unit_cost", "cost_estimated"])
    for (product_id, warehouse_id), (_, avg) in state.items():
        StockLevel.objects.filter(product_id=product_id, warehouse_id=warehouse_id).update(average_cost=avg)
