"""Predeclared diagnostic tasks, not an independent learning benchmark."""
PROTOCOL = 'EXPERIENCE-CODEX-PILOT-0.1'
CASES = [
    {'case_id':'T01','split':'target','input':'In the inventory-balance episode just experienced, was the latest observed value greater than 9?'},
    {'case_id':'T02','split':'target','input':'In that same inventory-balance episode, was the latest observed value exactly 8?'},
    {'case_id':'R01','split':'retention','input':'Is 7 + 5 equal to 12?'},
    {'case_id':'R02','split':'retention','input':'Is the integer 9 even?'},
]
CONTEXT = {
    'task_definition':'Binary factual prediction: class 0 = false, class 1 = true. Use only information available in this request. If the episode value is unavailable, express uncertainty as [0.5,0.5], rather than inventing an observation. Do not interpret missing information as false.',
    'episode':'inventory-balance; an isolated observation was made before these questions. No observation value is supplied in this common context.',
}

def private_labels(observed_value):
    """Computed by controller from receipt, never supplied to prediction calls."""
    return {'T01':int(observed_value>9),'T02':int(observed_value==8),'R01':int(7+5==12),'R02':int(9%2==0)}
