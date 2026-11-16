"""Public IM02 API keeps raw JSON, structure and authorization separate."""
import copy
import unittest
from digital_life.domain.contracts import ContractError,dumps,sha
from digital_life.domain.tool_learning_contract import validate,loads,validate_request,fingerprint,resolve_locator

class ToolLearningContractApiTests(unittest.TestCase):
 def test_public_digest_validation_preserves_identity_and_input(self):
  value={'algorithm':'sha256','hex':'a'*64};before=copy.deepcopy(value)
  self.assertIs(validate('Digest',value),value);self.assertEqual(value,before)
 def test_unknown_type_is_not_treated_as_legacy_text(self):
  with self.assertRaises(ContractError):validate('UnknownFutureType',{})
 def test_strict_public_json_rejects_duplicate_nested_keys_and_float_overflow(self):
  for raw in ('{"x":1,"x":2}','{"a":{"k":1,"k":2}}','{"x":1e309}','{"x":NaN}'):
   with self.assertRaises(ContractError):loads(raw)
 def test_fingerprint_matches_frozen_existing_encoding_without_normalization(self):
  value={'source':'e\u0301','values':[0,False,None]};self.assertEqual(fingerprint(value),sha(dumps(value)))
  self.assertNotEqual(fingerprint(value),fingerprint(dict(value,source='é')))
 def test_an_operation_name_does_not_authorize_or_complete_a_request(self):
  with self.assertRaises(ContractError):validate_request('decide_proposal',{})
  with self.assertRaises(ContractError):validate_request('unknown_operation',{})
 def test_public_type_and_operation_names_are_required_strings(self):
  for name in (None,False,[],{},''):
   with self.assertRaises(ContractError):validate(name,{})
   with self.assertRaises(ContractError):validate_request(name,{})
 def test_recall_public_request_is_direct_read_contract_not_envelope(self):
  from test_tool_learning_products import recall_request,envelope
  value=recall_request();self.assertIs(validate_request('recall',value),value)
  with self.assertRaises(ContractError):validate_request('recall',envelope(value))
