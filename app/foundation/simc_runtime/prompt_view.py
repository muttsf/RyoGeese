"""Pure Chinese presentation of one admitted offline result, never an executor."""
SKILLS={
    'voidform':'虚空形态','power_infusion':'能量灌注',
    'tentacle_slam':'触须猛击','vampiric_touch':'吸血鬼之触',
    'shadow_word_madness':'暗言术：癫','void_torrent':'虚空洪流',
    'shadow_word_pain':'暗言术：痛','void_volley':'虚空齐射',
    'void_blast':'虚空冲击','mind_blast':'心灵震爆',
    'shadow_word_death':'暗言术：灭','mind_flay':'精神鞭笞'}

def render_prompt(result):
    """No reading, filtering, mutation or additional model call."""
    modes=result['configuration']['burstModes']
    banner='；'.join(SKILLS[k]+('：暂缓' if v=='hold' else '：自动') for k,v in modes.items())
    skill=result.get('skill')
    held=[SKILLS[k] for k,v in modes.items() if v=='hold']
    note=('已暂缓'+ '、'.join(held)+'，其他技能继续按原顺序判断。') if held else '形态、灌注均可按原循环条件参与推荐。'
    if skill:
        reason=result['recommendation']['reason']
        prompt={'visible':True,'skillId':skill,'skillName':SKILLS[skill],
            'title':'建议：'+SKILLS[skill],'reason':reason,'controlBanner':banner,
            'controlNote':note,'canExecuteConfirmed':False,
            'evidenceNote':'保存资料的离线估算；建议不代表已经施放或当前可施放。',
            'interruptInstruction':None}
    else:
        codes=result.get('reasons',[])
        if codes==['IDENTICAL_RENDERED_STATE_NOT_NEW_SOURCE_PROOF']:
            title='本记录未产生新建议：重复显示已跳过'
        elif any('STOP' in x for x in codes):title='停止推荐'
        elif any('NO_TARGET' in x for x in codes):title='暂不推荐：明确无目标'
        else:title='暂不推荐：资料缺失、失效或不能通过核验'
        prompt={'visible':False,'skillId':None,'skillName':None,'title':title,
            'reason':title,'reasonCodes':list(codes),'controlBanner':banner,
            'controlNote':note,'canExecuteConfirmed':False,
            'evidenceNote':'不得继续显示本记录之前的技能作为新建议。',
            'interruptInstruction':None}
    return prompt
