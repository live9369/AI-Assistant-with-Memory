import unittest
class SharedStrings(unittest.TestCase):
 def test_roundtrip_and_literals(self):
  from digital_life.infrastructure.llm.compact_strings import compact_shared_strings,expand_shared_strings
  text='long source quotation with Unicode \u6765\u6e90 '*20
  original={'states':{'value':0.5,'fresh':True,'source_ref':'a'*32},'selected_memories':[{'content':text,'id':'a'*32}]*8,'cognition_sources':{'a'*32:text},'literal':[{'$s':0},{'$literal':[['key','value']]},None,False]}
  compact=compact_shared_strings(original)
  self.assertEqual(expand_shared_strings(compact),original)
  self.assertEqual(original['literal'][0],{'$s':0})
  self.assertEqual(compact['encoding'],'shared-strings-v4')
 def test_small_payload_not_rewritten(self):
  from digital_life.infrastructure.llm.compact_strings import compact_shared_strings
  payload={'task':'hello'};self.assertIs(compact_shared_strings(payload),payload)
if __name__=='__main__':unittest.main()
