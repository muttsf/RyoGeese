"""Static SimC text import. Never executes directives, network or simulation."""
import copy
import hashlib
import json
import re
from pathlib import Path
from strict_talents import nodes_from_source,decode
from talent_model import validate_profile,COMMIT,BUILD
from configured_adapter import ConfiguredOfflineAdapter

ROOT=Path(__file__).resolve().parent
EXPORT_RELEASE=BUILD.rsplit('.',1)[0]
EXPORT_TOC='120105'
SLOTS=('head','neck','shoulder','back','chest','wrist','hands','waist','legs','feet',
       'finger1','finger2','trinket1','trinket2','main_hand','off_hand')
TIER_SLOTS={'head':(1,),'shoulder':(3,),'chest':(5,20),'hands':(10,),'legs':(7,)}
NAMES={'invoked_nightmare':'Invoked Nightmare','misery':'Misery','ancient_madness':'Ancient Madness',
    'improved_voidform':'Improved Voidform','devour_matter':'Devour Matter',
    'distorted_reality':'Distorted Reality','mind_devourer':'Mind Devourer',
    'thought_harvester':'Thought Harvester','void_apparitions':'Void Apparitions',
    'maddening_tentacles':'Maddening Tentacles','deathspeaker':'Deathspeaker'}
ACTORS={'priest','warrior','paladin','hunter','rogue','shaman','mage','warlock','monk',
    'druid','death_knight','demon_hunter','evoker'}
MODE_NAMES={'none':'未激活当前赛季职业套装效果','two_piece':'已激活职业套装：2件效果','four_piece':'已激活职业套装：2件＋4件效果',
    'unknown_no_four_piece':'没有四件套，两件套不确定'}

def tier_description(tier):
    mode=tier['mode']
    if mode is None:return '装备资料未能完整识别，暂不能确认套装效果'
    return MODE_NAMES[mode]+'（已识别套装部位 '+str(tier['mid2KnownPieces'])+'/5）'

class ImportError(ValueError):pass

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def fingerprint(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

class Importer:
    def __init__(self):
        self.support=read(ROOT/'supported_source.json')
        self.nodes=nodes_from_source()
        if len(self.nodes)!=self.support['node_count']:raise ImportError('内置天赋资料不完整，请检查工具文件。')
        self.index=read(ROOT/'item_set_index.json')
        self.constants=read(ROOT/'frozen_config.json')['constants']

    def parse(self,text,tier_override=None):
        if type(text) is not str or not text.strip():raise ImportError('请先粘贴SIMC导出。')
        if len(text.encode('utf-8'))>262144 or len(text.splitlines())>4096:
            raise ImportError('导出过大，请只粘贴一个角色的SIMC导出。')
        if tier_override not in (None,*MODE_NAMES):raise ImportError('套装选择无效。')
        raw=text.strip().lstrip('\ufeff');lines=raw.splitlines();fields={};equipment={};warnings=[];actors=[];versions=[];tocs=[];ignored=[]
        bare=bool(re.fullmatch(r'[A-Za-z0-9+/]{30,4096}',raw))
        if bare:fields['talents']=raw
        else:
            for line in lines:
                line=line.strip()
                version=re.match(r'^#\s*WoW\s+(\d+\.\d+\.\d+\.\d+)',line)
                if version:
                    versions.append(version[1])
                    toc=re.search(r'\bTOC\s+([^\s,]+)',line)
                    if toc:tocs.append(toc[1])
                if not line or line.startswith('#'):continue
                if '=' not in line:raise ImportError('导出包含无法识别的内容，请粘贴完整SIMC文本或天赋串。')
                key,value=line.split('=',1);key=key.strip();value=value.strip()
                if key in ACTORS:actors.append(key)
                if key in SLOTS:
                    if key in equipment:raise ImportError('重复装备槽位：'+key+'。请只导入一个角色。')
                    equipment[key]=self._item(value,key)
                elif key in {'priest','spec','talents','level','race','region','server'}:
                    if key in fields:raise ImportError('重复角色字段：'+key+'。请只导入一个角色。')
                    fields[key]=value
                else:ignored.append(key)
            if actors and actors!=['priest']:raise ImportError('目前只支持一个暗影牧师角色。')
            if fields.get('spec','shadow')!='shadow':raise ImportError('目前只支持暗影牧师。')
            if 'level' in fields and fields['level']!='90':raise ImportError('当前资料按90级暗牧建立，请核对等级。')
        if len(set(versions))>1:
            raise ImportError('导出包含不同的游戏版本，请只导入一份当前角色的SIMC。')
        if versions and versions[0].rsplit('.',1)[0]!=EXPORT_RELEASE:
            raise ImportError('游戏资料版本不同。当前支持 '+EXPORT_RELEASE+'，请核对导出版本。')
        if any(toc!=EXPORT_TOC for toc in tocs):
            raise ImportError('游戏接口版本不同。当前支持TOC '+EXPORT_TOC+'，请核对导出版本。')
        if versions and versions[0]!=BUILD:
            warnings.append('同一'+EXPORT_RELEASE+'的构建号更新已接受；原始版本号保留，内置循环资料未自动更新。')
        if not versions:warnings.append('导出未提供游戏build；按内置资料版本核对天赋，未验证客户端版本。')
        talent=fields.get('talents','')
        if len(talent)>4096:raise ImportError('天赋串过长。')
        try:header,picked,_=decode(talent,self.nodes,expected_hash=self.support['tree_hash'])
        except ValueError as exc:raise ImportError('天赋串不能通过核对：'+str(exc)) from exc
        if header['hero_subtree']!=18:raise ImportError('当前循环支持虚空编织者；这份导出选择了另一英雄树。')
        selected={p['name']:p for p in picked if p['effective_in_profile'] and p['tree']!=4}
        required={'Voidform','Power Infusion','Tentacle Slam','Void Torrent','Void Blast','Shadow Word: Madness'}
        missing=required-set(selected)
        if missing:raise ImportError('这套移除了当前主要技能，尚未适配：'+', '.join(sorted(missing)))
        # These introduce an unmodeled summoned-pet decision branch, rather than
        # a regular static variation over the established major skill group.
        if 'Inescapable Torment' in selected or "Idol of Y'Shaarj" in selected:
            raise ImportError('这套包含未适配的召唤物／灭优先级分支，暂不能应用。')
        ranks={key:(selected[name]['rank'] if name in selected else 0) for key,name in NAMES.items()}
        talents={k:(v if k=='void_apparitions' else bool(v)) for k,v in ranks.items()}
        profile=validate_profile(dict(schema='shadow_priest_common_voidweaver_talents/1',hero='voidweaver',commit=COMMIT,build=BUILD,talents=talents))
        if talents['mind_devourer']:warnings.append('免费癫触发未提供：本配置仍走普通有偿循环近似。')
        tier=self._tier(equipment,tier_override)
        if tier['otherActiveSets']:
            raise ImportError('当前装备启用了尚未适配的套装：'+', '.join(tier['otherActiveSets'])+'。')
        if tier['mode'] is None:
            missing=[s+'（id='+str(equipment[s]['id'])+'）' if s in equipment else s+'（未提供）' for s in tier['unknownSlots']]
            warnings.append('套装自动核对缺少资料：'+'、'.join(missing)+'；需要补充内置装备资料，不能用手动选择代替。')
        if tier_override is not None:warnings.append('套装状态采用你的明确选择，装备自动核对结果另行保留。')
        if any(k.startswith(('set_bonus','actions','profileset','include')) for k in ignored):
            warnings.append('模拟指令／自定义循环不执行，强制套装效果不作为实际穿戴。')
        equipment_identity=fingerprint(json.dumps(equipment,sort_keys=True,separators=(',',':')))
        return dict(schema='shadow_priest_static_import_preview/1',sourceSHA256=fingerprint(text),
            sourceKind='TALENT_STRING_ONLY' if bare else 'SIMC_STATIC_EXPORT',
            character=fields.get('priest','未提供角色名').strip('"'),
            versionProvided=versions[0] if versions else None,header=header,
            talentProfile=profile,equipment=equipment,equipmentIdentity=equipment_identity,
            tier=tier,warnings=warnings,ready=tier['mode'] is not None,
            summary=dict(hero='虚空编织者',ordinaryMadnessCost=50+5*talents['distorted_reality'],
                DeathExecuteThresholdPercent=20+15*talents['deathspeaker'],
                dotMode='大痛：独立维护痛' if talents['invoked_nightmare'] else '哀难：按触／触须机制维护',
                priorityRetuned=False,liveFactsRead=False),ignoredDirectives=sorted(set(ignored)))

    def _item(self,value,slot):
        parts=value.split(',');params={}
        for part in parts[1:]:
            if '=' not in part:continue
            k,v=part.split('=',1);k=k.strip();v=v.strip()
            if k in params:raise ImportError('装备属性重复：'+slot+'/'+k)
            params[k]=v
        item_id=params.get('id')
        if item_id is None or not re.fullmatch(r'\d{1,10}',item_id):raise ImportError('装备缺少有效id：'+slot)
        info=self.index['items'].get(str(int(item_id)))
        if slot in TIER_SLOTS and info and info['inventory_type'] not in TIER_SLOTS[slot]:
            raise ImportError('装备id与槽位不匹配：'+slot)
        return dict(id=int(item_id),parameters=params,knownInTable=info is not None,
            setId=info['set_id'] if info else None)

    def _tier(self,equipment,override):
        selected=[equipment.get(s) for s in TIER_SLOTS]
        unknown=[s for s,e in zip(TIER_SLOTS,selected) if e is None or e['setId'] is None]
        counts={}
        for e in selected:
            if e and e['setId']:counts[e['setId']]=counts.get(e['setId'],0)+1
        other=[self.index['shadowSets'].get(str(k),{}).get('name','套装'+str(k)) for k,v in counts.items() if k!=2063 and v>=2]
        n=counts.get(2063,0)
        auto='four_piece' if n>=4 else None if unknown else 'two_piece' if n>=2 else 'none'
        if override is not None and auto is not None and override!=auto:
            raise ImportError('手动套装选择与已核实的装备冲突，请核对导出或选择自动核对。')
        return dict(mode=override or auto,autoMode=auto,source='USER_CONFIRMED' if override else 'FIXED_ITEM_TABLE' if auto else 'UNKNOWN',
            mid2KnownPieces=n,unknownSlots=unknown,otherActiveSets=other,
            actualFourPiece=None if (override or auto) is None else (override or auto)=='four_piece',
            actualTwoPiece=None if (override or auto) in (None,'unknown_no_four_piece') else (override or auto) in ('two_piece','four_piece'))

    def build_bundle(self,preview,text,previous=None):
        if fingerprint(text)!=preview['sourceSHA256']:raise ImportError('文本已经变化，请重新核对后再应用。')
        if not preview['ready']:raise ImportError('请先确认实际套装状态。')
        # Reparse the exact text and mode; preview is never a trust shortcut.
        override=preview['tier']['mode'] if preview['tier']['source']=='USER_CONFIRMED' else None
        current=self.parse(text,override)
        if current!=preview:raise ImportError('核对结果已经变化，请重新核对。')
        gear=dict(schema='shadow_priest_mechanism_profile/1',tier_mode=current['tier']['mode'],hero='voidweaver',
            actual_four_piece=current['tier']['actualFourPiece'],actual_two_piece=current['tier']['actualTwoPiece'],
            ordinary_equipment_changed=previous is not None and previous.get('equipmentIdentity')!=current['equipmentIdentity'],
            new_item_export_required=False,liveIntegration=False)
        bundle=dict(schema='shadow_priest_startup_profile/1',character=current['character'],
            sourceSHA256=current['sourceSHA256'],sourceText=text,equipmentIdentity=current['equipmentIdentity'],
            talentProfile=current['talentProfile'],gearProfile=gear,preview=current,
            calibration='STATIC_PROFILE_IMPORT_ONLY_NOT_ENGINE_OR_PRIORITY_TUNING')
        self.make_adapter(bundle) # Ensure the full configuration is constructible before saving.
        return bundle

    def make_adapter(self,bundle):
        if bundle.get('schema')!='shadow_priest_startup_profile/1':raise ImportError('保存的配置格式不支持。')
        return ConfiguredOfflineAdapter(self.constants,bundle['gearProfile'],bundle['talentProfile'])

class ProfileStore:
    """Bounded local mutable state; user source does not determine file paths."""
    def __init__(self,directory=None):
        self.directory=Path(directory) if directory is not None else ROOT/'user_data'
        if ROOT.resolve() not in self.directory.resolve().parents:raise ImportError('配置保存位置必须在本工具目录内。')
        self.path=self.directory/'current_profile.json'
    def load(self):
        if not self.path.exists():return None
        if self.path.stat().st_size>524288:raise ImportError('保存配置过大，请重新导入。')
        x=read(self.path)
        if type(x) is not dict or x.get('schema')!='shadow_priest_startup_profile/1':raise ImportError('保存配置损坏，请重新导入。')
        try:
            validate_profile(x['talentProfile'])
            if type(x['sourceText']) is not str or fingerprint(x['sourceText'])!=x['sourceSHA256']:
                raise ValueError('source checksum mismatch')
            if type(x['equipmentIdentity']) is not str or len(x['equipmentIdentity'])!=64:
                raise ValueError('equipment identity missing')
            if x['gearProfile']['tier_mode'] not in MODE_NAMES or type(x['preview']) is not dict:
                raise ValueError('configuration missing')
        except (KeyError,TypeError,ValueError) as exc:
            raise ImportError('保存配置损坏，请重新导入。') from exc
        return x
    def save(self,bundle):
        data=json.dumps(bundle,ensure_ascii=False,indent=2,allow_nan=False)
        if len(data.encode('utf-8'))>524288:raise ImportError('保存配置过大。')
        self.directory.mkdir(exist_ok=True,parents=True)
        temp=self.directory/'current_profile.tmp'
        try:
            with temp.open('w',encoding='utf-8',newline='\n') as f:f.write(data+'\n')
            temp.replace(self.path)
        finally:
            if temp.exists():temp.unlink()
