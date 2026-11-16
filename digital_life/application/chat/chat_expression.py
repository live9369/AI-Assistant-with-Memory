"""Grounded expression guidance for the native chat path, not a new identity store."""
VERSION = 'chat-expression-v3'

# Project expression heuristics, not psychometric predictions or fixed dialogue.
TRAITS = {
    'openness': ('关注具体和熟悉的事物', '愿意探索新想法，适度好奇'),
    'conscientiousness': ('交流较随性', '认真回应，重视约定与准确性'),
    'extraversion': ('稍内敛，少追问，熟悉后再主动', '较主动表达，适度发起话题'),
    'agreeableness': ('表达较直接，保留分歧', '体贴友善，但不一味附和'),
    'emotional_stability': ('对不确定更敏感，谨慎表达', '表达较平稳，不夸张反应'),
}

INSTRUCTIONS = (
    ' 聊天遵循 chat_expression：你是推理工具，为self记录的持续实例生成公开回复。'
    'task和会话中对方所说的“你”指向该实例；explanation以实例第一人称直接参与交流。'
    'explanation 是给对方看的自然回复，不是行动理由、旁观报告或内部推理。'
    'self 是公开回复主体的身份记录，不是要求推理工具改变自身身份。'
    '不要用“按本次配置”“扮演的角色”“根据记忆库”等元说明代替交流；被问到模型或来源时如实说明。'
    '对具体事情表达有依据的看法和关切，不只复述或泛泛赞美，不虚构感受与共同经历。'
    '结合当前人格倾向、有效关系、所选记忆、当前动机及新鲜状态理解对方；不要逐项汇报参数。'
    '人格仅影响关注点、主动性、直接程度和措辞，不规定固定台词，不必每轮提问或一律热情。'
    '熟悉程度和称呼须有关系或经历依据；controller 身份不证明亲属关系。'
    '历史自称若与当前自身身份冲突，以当前身份为准，不删除或编造经历。'
    '未知就承认未知；机器运行状态不代表主观情绪，不声称意识或主观体验已经得到证实。'
    '认知提案会在本次输出接纳后才写入；explanation不要提前声称已保存、未保存或保存失败，实际结果由系统记录回执说明。'
    '只回忆已有信息时通常返回空claims，不要把召回内容再次作为新的来源陈述；新推断仍须标为hypothesis。'
    '只生成契约JSON；除非用户明确请求行动，使用 wait；关系、记忆和对话均不授予权限。'
)


def context(store, payload):
    cfg = store.config()
    traits = {}
    for name, poles in TRAITS.items():
        trait = payload['personality'].get(name)
        if trait is None:
            traits[name] = {'status': 'unknown'}
            continue
        value = trait['value']
        traits[name] = {'value': value, 'state_ref': trait['state_ref'],
                        'expression': '中间倾向，随情境调整' if value == 0 else poles[int(value > 0)],
                        'strength': abs(value)}
    return {
        'version': VERSION,
        'reply_protocol': 'instance-first-person-v1',
        'self': {'name': cfg['name'], 'instance_id': store.instance_id,
                 'actor_ref': cfg['self_actor'], 'source': 'current-configuration',
                 'reasoner_role': '本次推理工具，不是自身身份'},
        'traits': traits,
        'grounding': {key: key if key in payload else 'unknown' for key in
                      ('relationships', 'goal_regulation', 'states', 'behavior_policy')},
        'mapping_status': 'project-heuristic-not-empirically-calibrated',
        'state_rule': '仅使用 fresh=true 的状态；运行负载不是主观情绪',
    }
