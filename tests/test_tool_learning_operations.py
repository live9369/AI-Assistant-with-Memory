"""All frozen operation request forms through the public pure contract API."""
import copy
import unittest
from digital_life.domain.contracts import ContractError
from digital_life.domain.tool_learning_contract import validate_request
from digital_life.domain.tool_learning_products import OPERATIONS
from test_tool_learning_products import payloads,envelope,sl,ref

class ToolLearningOperationApiTests(unittest.TestCase):
 def test_public_request_registry_exactly_covers_frozen_operations(self):
  values=payloads();self.assertEqual(set(values),set(OPERATIONS));self.assertEqual(len(values),10)
  for operation,payload in values.items():
   with self.subTest(operation=operation):
    v=copy.deepcopy(payload) if operation=='recall' else envelope(copy.deepcopy(payload))
    if operation=='admit_observation':v['work_ref']=sl()
    before=copy.deepcopy(v);self.assertIs(validate_request(operation,v),v);self.assertEqual(v,before)
 def test_each_operation_rejects_extra_top_level_contract_fields(self):
  for operation,payload in payloads().items():
   v=copy.deepcopy(payload) if operation=='recall' else envelope(copy.deepcopy(payload))
   if operation=='admit_observation':v['work_ref']=sl()
   v['pretend_authorized']=True
   with self.subTest(operation=operation),self.assertRaises(ContractError):validate_request(operation,v)
 def test_admit_new_work_and_write_existing_work_are_distinct(self):
  values=payloads();v=envelope(values['admit_observation'])
  with self.assertRaises(ContractError):validate_request('admit_observation',v)
  v=envelope(values['resume_work']);v['work_ref']=sl()
  with self.assertRaises(ContractError):validate_request('resume_work',v)
 def test_read_request_never_requires_a_write_envelope(self):
  v=payloads()['recall'];self.assertIs(validate_request('recall',v),v)
  with self.assertRaises(ContractError):validate_request('recall',envelope(v))
 def test_repeated_logical_work_and_purpose_must_agree(self):
  for operation in ('resume_work','record_effect'):
   v=envelope(copy.deepcopy(payloads()[operation]));v['payload']['work']['id']='different-work'
   with self.subTest(operation=operation),self.assertRaises(ContractError):validate_request(operation,v)
  v=envelope(copy.deepcopy(payloads()['admit_observation']));v['work_ref']=sl();v['principal']['purpose']='evaluate'
  with self.assertRaises(ContractError):validate_request('admit_observation',v)
