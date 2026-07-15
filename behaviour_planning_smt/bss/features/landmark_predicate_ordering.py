import z3
from behaviour_planning_smt.bss.features.base import DimensionConstructorSMT

class LandmarkPredicatesOrderingSMT(DimensionConstructorSMT):
    
    def __init__(self, name, task, additional_information):
        self.landmark_predciates_vars = []
        self.dummy_landmark_variable = z3.Bool(f'dummy-{name}-variable', ctx=task.encoder.ctx)
        self.dummy_landmark_expression = self.dummy_landmark_variable == z3.BoolVal(False, ctx=task.encoder.ctx)
        super().__init__(name, task, additional_information)

    def __encode__(self, encoder):
        """!
        This function should return the encoding of the dimension.
        """
        landmark_vars_dict = self.addinfo.get('landmark_vars_dict', [])
        assert len(landmark_vars_dict) > 0, 'LandmarkPredicatesOrderingSMT requires the landmark_vars_list to be provided in the additional_information.'
        _landmark_z3_vars = []
        for _, landmark_vars_list in landmark_vars_dict.items():
            landmark_name = str(landmark_vars_list[0])[:str(landmark_vars_list[0]).rfind('_')]
            landmark_z3_var = z3.Int(f'{self.name}-{landmark_name}', ctx=encoder.ctx)
            _landmark_z3_vars.append(landmark_z3_var)
            for idx, predicate in enumerate(landmark_vars_list):
                expr  = [predicate] + [z3.Not(predicate, ctx=encoder.ctx) for predicate in landmark_vars_list[:idx]]
                self.formula.append(z3.And(expr) == (landmark_z3_var == z3.IntVal(idx+1, ctx=encoder.ctx)))
            self.formula.append(z3.And([z3.Not(predicate, ctx=encoder.ctx) for predicate in landmark_vars_list]) == (landmark_z3_var == z3.IntVal(-100, ctx=encoder.ctx)))

        uf_gt = z3.Function(f'{self.name}PredicateOrderingFn', z3.IntSort(ctx=encoder.ctx), z3.IntSort(ctx=encoder.ctx), z3.BoolSort(ctx=encoder.ctx)) 
        for i, landmark_i in enumerate(_landmark_z3_vars):
            for j, landmark_j in enumerate(_landmark_z3_vars[i+1:]):
                self.formula.append((landmark_i >= landmark_j) == (uf_gt(landmark_i, landmark_j) == z3.BoolVal(True,  ctx=encoder.ctx)))
                self.formula.append((landmark_i < landmark_j)  == (uf_gt(landmark_i, landmark_j) == z3.BoolVal(False, ctx=encoder.ctx)))
                # now create a variable to hold this ordering.
                ordering_var = z3.Int(f'{self.name}-predicate-ordering-{str(landmark_i)}__after__{str(landmark_j)}'.replace('(','_').replace(')',''), ctx=encoder.ctx)
                self.formula.append(ordering_var == uf_gt(landmark_i, landmark_j))
                self.landmark_predciates_vars.append(ordering_var)

    def expr(self, model):
        ret_value = []
        ret_value_str = []
        for predicate in self.landmark_predciates_vars:
            predicate_value = model.evaluate(predicate, model_completion = True)
            ret_value.append(predicate == predicate_value)
            ret_value_str.append(str(predicate_value.as_long()))
        self.var_domain.add(''.join(ret_value_str))
        if len(ret_value) == 0: ret_value.append(self.dummy_landmark_expression)
        return z3.And(ret_value)
