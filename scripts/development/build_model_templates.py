"""Ship the reviewed configuration examples with the installed management panel."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
NAMES={'ollama.example.json':'本地 Ollama','llamacpp.example.json':'本地 llama.cpp',
       'remote-chat.example.json':'远程 JSON Schema','remote-json-object.example.json':'远程 JSON Object'}

def main():
    items=[{'id':name,'label':label,'configuration':json.loads((ROOT/'config/examples/llm'/name).read_text())} for name,label in NAMES.items()]
    (ROOT/'digital_life/resources/model-templates.json').write_text(json.dumps({'items':items},ensure_ascii=False,indent=2)+'\n')
    print('Generated packaged model templates; no instance accessed.')

if __name__=='__main__': main()
