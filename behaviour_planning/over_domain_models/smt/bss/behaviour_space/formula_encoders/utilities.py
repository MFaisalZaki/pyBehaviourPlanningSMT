import z3

def flattern_expression(expr):
    if len(expr.children()) == 1 and (z3.is_and(expr) or z3.is_or(expr)):
        return flattern_expression(expr.arg(0))
    return expr if (z3.is_and(expr) or z3.is_or(expr)) else z3.And([expr])