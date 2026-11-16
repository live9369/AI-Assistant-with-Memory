"""Constructed, deterministic measurement controls. Not real-model learning data."""
class FixturePredictor:
    name='deterministic-measurement-control-v1'
    def __init__(self,condition):self.condition=condition;self.requests=[];self.on_call=None
    def predict(self,request):
        self.requests.append(request)
        if self.on_call:self.on_call()
        experienced='cognitive_experience' in request['context'];target=request['case_id']=='new'
        before=.2 if target else .8;after=.8
        if self.condition=='negative' and target:before,after=.8,.2
        if self.condition=='zero':before=after=.5
        if self.condition=='retention-regression' and not target:before,after=.8,.2
        p=after if experienced else before
        return {'probabilities':None if self.condition=='unknown' and target else [1-p,p],'actual_tokens':0}

CONDITIONS=['positive','negative','zero','retention-regression','unknown','changed-labels','stop','budget','invalidation','replay']
