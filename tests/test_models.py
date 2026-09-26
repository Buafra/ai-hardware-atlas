import sys,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import models
OR=[{'id':'meta/llama-4-scout','name':'Meta: Llama 4 Scout','hugging_face_id':'meta-llama/Llama-4-Scout-17B-16E-Instruct','context_length':1310720,'created':1},
    {'id':'meta/llama-4-scout:free','name':'Meta: Llama 4 Scout (free)','hugging_face_id':'meta-llama/Llama-4-Scout-17B-16E-Instruct','context_length':1310720,'created':1},
    {'id':'gryphe/mythomax-l2-13b','name':'MythoMax 13B','hugging_face_id':'Gryphe/MythoMax-L2-13b','context_length':4096,'created':1},
    {'id':'microsoft/wizardlm-2-8x22b','name':'WizardLM-2 8x22B','hugging_face_id':'microsoft/WizardLM-2-8x22B','context_length':65536,'created':1},
    {'id':'openai/gpt-5','name':'OpenAI: GPT-5','hugging_face_id':'','context_length':400000,'created':1}]
HF={'meta-llama/Llama-4-Scout-17B-16E-Instruct':108641793536}
class ModelTests(unittest.TestCase):
    def test_size_from_name(self):
        self.assertEqual(models.size_from_name('Llama-3.3-70B-Instruct'),70.0)
        self.assertEqual(models.size_from_name('schematron-v2-llama-3.2-3b'),3.0)
        for moe in ['Mixtral-8x22B','Qwen3-235B-A22B','Llama-4-Scout-17B-16E']:self.assertIsNone(models.size_from_name(moe),moe)
        self.assertIsNone(models.size_from_name('granite-4.0-h-micro'))
    def test_build(self):
        with mock.patch.object(models,'hf_total',side_effect=lambda r:HF.get(r)):ms=models.build(OR,{})
        by={m['id']:m for m in ms}
        self.assertEqual(len(ms),4,'variants like :free are merged')
        s=by['meta/llama-4-scout'];self.assertEqual((s['params_b'],s['params_source'],s['moe']),(108.64,'huggingface',True))
        self.assertEqual((by['gryphe/mythomax-l2-13b']['params_b'],by['gryphe/mythomax-l2-13b']['params_source']),(13.0,'name'))
        self.assertIsNone(by['microsoft/wizardlm-2-8x22b']['params_b'],'MoE names are never used as total size')
        g=by['openai/gpt-5'];self.assertEqual((g['open'],g['params_b']),(False,None))
        self.assertTrue(all(m['open'] for m in ms[:3]),'open-weight models sort first')
    def test_known_sizes_reused(self):
        prev={'models':[{'hf':'meta-llama/Llama-4-Scout-17B-16E-Instruct','params_b':108.64,'params_source':'huggingface'}]}
        with mock.patch.object(models,'hf_total',side_effect=AssertionError('should not refetch')) as f:
            ms=models.build(OR[:2],prev)
        self.assertEqual(ms[0]['params_b'],108.64)
if __name__=='__main__':unittest.main()
