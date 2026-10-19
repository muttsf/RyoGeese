using System.Text.Json;
using System.Text.RegularExpressions;

namespace GpuDash;

internal record Fact(string name,string scope,string status,object? value,string reason,string raw_text,double? confidence);
internal record RetryTrace(string cell,ReadToken first,ReadToken? native,ReadToken mask,bool accepted);
internal record ReadResult(Fact[] facts,Geometry geometry,string[] faults,double milliseconds,RetryTrace[]? retries=null);
internal sealed class Reader:IDisposable
{
    readonly JsonElement layout;
    readonly KernelModule kernels;
    readonly Ocr ocr;
    readonly string[] cells;
    readonly string[] cellRows;
    readonly HashSet<string> captions;
    internal static readonly string[] EffectRows={"B1","B2","B3","D1","D2","D3"};
    readonly Dictionary<string,int> indices;
    readonly string[] refNames;
    readonly DeviceBuffer jobs=new(128*6*4),regionOutput=new(128*4*4,true);
    readonly DeviceBuffer band,scratch,images,metadata,refPixels,refSpecs,templateOutput;
    internal Reader(JsonElement assets,KernelModule kernels,int device,string profileRoot) {
        layout=assets.GetProperty("layout");this.kernels=kernels;
        cells=layout.GetProperty("fields").EnumerateObject().Select(x=>x.Value.TryGetProperty("cell",out var c)?c.GetString():null).Where(x=>x!=null).Cast<string>().Distinct().ToArray();
        cellRows=cells.Select(x=>x.Split('_')[0]).ToArray();
        captions=layout.GetProperty("captionCells").EnumerateObject().Select(x=>x.Name).ToHashSet();
        indices=cells.Select((name,i)=>(name,i)).ToDictionary(x=>x.name,x=>x.i);
        band=new(cells.Length*80*80*3);scratch=new(cells.Length*80*80*2*4);images=new(cells.Length*3*160*160*3);metadata=new(cells.Length*12*4,true);
        var refs=assets.GetProperty("tokens").GetProperty("samples").EnumerateArray().Concat(assets.GetProperty("fontTokens").GetProperty("samples").EnumerateArray()).ToArray();
        refNames=refs.Select(x=>x.GetProperty("token").GetString()!).ToArray();
        var pixels=new List<byte>();var sizes=new List<int>();
        foreach(var r in refs) {
            var mask=r.GetProperty("mask").EnumerateArray().Select(x=>x.GetString()!).ToArray();
            sizes.AddRange(new[]{pixels.Count,mask[0].Length,mask.Length});pixels.AddRange(string.Concat(mask).Select(x=>(byte)(x=='1'?1:0)));
        }
        refPixels=new(pixels.Count);refPixels.Upload(pixels.ToArray());refSpecs=new(sizes.Count*4);refSpecs.Upload(sizes.ToArray());templateOutput=new(cells.Length*refs.Length*4,true);
        ocr=new Ocr(assets,kernels,device,profileRoot);
    }
    internal double Warm()=>ocr.Warm();
    double[] Rect(string key)=>layout.GetProperty("cells").GetProperty(key).EnumerateArray().Select(x=>x.GetDouble()).ToArray();
    static double[] ArrayRect(JsonElement e)=>e.EnumerateArray().Select(x=>x.GetDouble()).ToArray();
    internal ReadResult Read(DeviceBuffer image,int w,int h,Geometry geometry) {
        var timer=System.Diagnostics.Stopwatch.StartNew();var global=new List<string>();var rowFault=new Dictionary<string,string>();
        if(geometry.Variant!="D_VISIBLE")global.Add("PROFILE_MISMATCH_D_HIDDEN");
        if(geometry.Scale<1.3||geometry.Scale>1.46)global.Add("SCALE_OUT_OF_CAL_RANGE");
        if(geometry.Left<0||geometry.Top<0||geometry.Left+578*geometry.Scale>w||geometry.Top+306*geometry.Scale>h)global.Add("DASH_CLIPPED");
        if(global.Count!=0)return Failed(geometry,string.Join(';',global),timer.Elapsed.TotalMilliseconds);
        var checks=new List<(string key,int kind,int[] rect,int extra)>();
        foreach(var r in new (string,double[])[]{("TL",new double[]{8,292,8,8}),("L_vertical",new double[]{403,261,3,10}),("L_bottom",new double[]{403,261,10,3}),("BR1",new double[]{561,12,10,3}),("BR2",new double[]{561,6,10,3})})
            checks.Add((r.Item1,0,geometry.Pixels(r.Item2),0));
        foreach(var row in layout.GetProperty("rows").EnumerateObject().Where(x=>!x.Name.StartsWith('C')))
            checks.Add((row.Name,1,geometry.Pixels(ArrayRect(row.Value)),0));
        foreach(var key in new[]{"C1label","C1value","C1locator","C2label","C2current","C2max"})checks.Add((key,1,geometry.Pixels(Rect(key)),0));
        foreach(var col in new (string,int)[]{("AB",145),("BC",287),("CD",431)}){
            int y=(int)Math.Round(geometry.Top+geometry.Scale*20),end=(int)Math.Round(geometry.Top+geometry.Scale*288);
            checks.Add((col.Item1,2,new[]{(int)Math.Round(geometry.Left+geometry.Scale*col.Item2),y,1,end-y},0));
        }
        foreach(var row in layout.GetProperty("healthSearchRegions").EnumerateObject())
            checks.Add(("health:"+row.Name,3,geometry.Pixels(ArrayRect(row.Value.GetProperty("searchRect"))),Math.Max(1,(int)Math.Round(4*geometry.Scale))));
        foreach(var row in EffectRows) {
            checks.Add(("icon:"+row,5,geometry.Pixels(Rect(row+"_icon")),0));
            checks.Add(("name:"+row,4,geometry.Pixels(ArrayRect(layout.GetProperty("nameSearchRegions").GetProperty(row).GetProperty("searchRect"))),0));
        }
        var ints=checks.SelectMany(j=>new[]{j.kind,j.rect[0],j.rect[1],j.rect[2],j.rect[3],j.extra}).ToArray();jobs.Upload(ints);
        kernels.Run("regions",checks.Count,Cuda.Ptr(image.Pointer),(ulong)w,(ulong)h,Cuda.Ptr(jobs.Pointer),(ulong)checks.Count,Cuda.Ptr(regionOutput.Pointer));
        var values=regionOutput.Metadata<float>(checks.Count*4);var measures=new Dictionary<string,float[]>();
        for(int i=0;i<checks.Count;i++){
            var check=checks[i];float[] v=values.Skip(4*i).Take(4).ToArray();measures[check.key]=v;
            if(check.kind==0&&v[0]<.8)global.Add("MARKER_MISMATCH_"+check.key);
            if(check.kind==1&&v.Any(x=>x<.82))rowFault[check.key]="ROW_BORDER_MISSING_OR_OCCLUDED";
            if(check.kind==2&&v[0]<.82)global.Add("COLUMN_DIVIDER_MISMATCH_"+check.key);
        }
        if(global.Count!=0)return Failed(geometry,string.Join(';',global),timer.Elapsed.TotalMilliseconds);
        int margin=Math.Max(2,(int)Math.Round(1.5*geometry.Scale));
        jobs.Upload(cells.SelectMany(c=>geometry.Pixels(Rect(c)).Concat(new[]{margin,captions.Contains(c)?Math.Max(1,(int)Math.Round(22*geometry.Scale))-margin:0})).ToArray());
        kernels.Run("prepare_cells",cells.Length,Cuda.Ptr(image.Pointer),(ulong)w,(ulong)h,Cuda.Ptr(jobs.Pointer),(ulong)cells.Length,Cuda.Ptr(band.Pointer),Cuda.Ptr(scratch.Pointer),Cuda.Ptr(images.Pointer),Cuda.Ptr(metadata.Pointer));
        var meta=metadata.Metadata<int>(cells.Length*12);
        kernels.Run("template_scores",cells.Length*refNames.Length,Cuda.Ptr(images.Pointer),Cuda.Ptr(metadata.Pointer),(ulong)cells.Length,Cuda.Ptr(refPixels.Pointer),Cuda.Ptr(refSpecs.Pointer),(ulong)refNames.Length,Cuda.Ptr(templateOutput.Pointer));
        var match=templateOutput.Metadata<float>(cells.Length*refNames.Length);
        var presence=new Dictionary<string,bool?>();var presenceReason=new Dictionary<string,string>();
        foreach(var row in EffectRows){
            float frac=measures["icon:"+row][0],bright=measures["name:"+row][0];bool empty=meta[indices[row+"_value"]*12]!=0;
            presence[row]=frac>.15?true:frac<.01&&bright<3&&empty?false:null;
            presenceReason[row]=presence[row]==true?"ICON_CONTENT":presence[row]==false?"NORMAL_COMPLETE_BLANK":"CONTENT_OR_BLANK_CONFLICT";
        }
        var tokens=new Dictionary<int,ReadToken>();var need=new List<(int cell,int mode)>();
        for(int i=0;i<cells.Length;i++){
            string row=cellRows[i];if(presence.GetValueOrDefault(row)==false||meta[i*12]!=0)continue;
            var ranked=Enumerable.Range(0,refNames.Length).GroupBy(j=>refNames[j]).Select(g=>(token:g.Key,score:g.Max(j=>match[i*refNames.Length+j]))).OrderByDescending(x=>x.score).ToArray();
            if(ranked[0].score>=.965&&ranked[0].score-(ranked.Length>1?ranked[1].score:0)>=.04)tokens[i]=new(ranked[0].token,ranked[0].score,"GPU_CAL_TOKEN_TEMPLATE");
            else if(meta[i*12+1]==0)need.Add((i,meta[i*12+2]==0?0:1));
        }
        foreach(var t in ocr.Read(images,meta,need))tokens[t.Key]=t.Value;
        var retry=need.Where(x=>x.mode==0&&tokens[x.cell].Confidence<.85&&Regex.IsMatch(tokens[x.cell].Text,@"^[0-9]+$")&&meta[x.cell*12+3]==tokens[x.cell].Text.Length&&meta[x.cell*12+4]==0).Select(x=>(x.cell,1)).ToList();
        var secondary=ocr.Read(images,meta,retry);
        foreach(var t in secondary)if(t.Value.Text==tokens[t.Key].Text&&t.Value.Confidence>=.85)tokens[t.Key]=t.Value with{Method="GPU_NUMERIC_CONFIRMED_RETRY"};
        // Bounded same-image agreement: A2 charges, effect zeros, A5 two-digit CD.
        // The numeric result must agree; never infer values from prior facts.
        var masked=need.Where(x=>MaskCandidate(cells[x.cell],x.mode,tokens[x.cell],secondary.GetValueOrDefault(x.cell),meta,x.cell)).Select(x=>(x.cell,2)).ToList();
        var traces=new List<RetryTrace>();
        foreach(var t in ocr.Read(images,meta,masked)) {
            var first=tokens[t.Key];bool accepted=t.Value.Text==first.Text&&t.Value.Confidence>=.85;
            traces.Add(new(cells[t.Key],first,secondary.GetValueOrDefault(t.Key),t.Value,accepted));
            if(accepted)tokens[t.Key]=t.Value with{Method=cells[t.Key]=="A2_chg"?"GPU_A2_MASK_AGREEMENT_RETRY":cells[t.Key]=="A5_value"?"GPU_A5_MASK_AGREEMENT_RETRY":"GPU_ZERO_MASK_AGREEMENT_RETRY"};
        }
        var facts=new List<Fact>();
        foreach(var field in layout.GetProperty("fields").EnumerateObject()){
            string name=field.Name,row=name.Split('.')[0],cell=field.Value.TryGetProperty("cell",out var c)?c.GetString()!:field.Value.GetProperty("iconCell").GetString()!;
            string scope=field.Value.GetProperty("scope").GetString()!;
            ReadToken token=indices.TryGetValue(cell,out int index)?tokens.GetValueOrDefault(index,new("",0,"UNREAD")):new("",0,"UNREAD");
            string? fault=row.StartsWith('C')?rowFault.GetValueOrDefault(cell)??rowFault.GetValueOrDefault(row+"label"):rowFault.GetValueOrDefault(row);
            float health=measures.GetValueOrDefault("health:"+row,new float[4])[0];
            object? value=null;string reason,status="unknown";
            if(fault!=null)reason=fault;
            else if(health is 2 or 3)reason="PLUGIN_HEALTH_ERROR_OR_UNREADABLE";
            else if(health==1&&(name=="A7.uses"||name.EndsWith(".seconds")))reason="PLUGIN_FIELD_DEGRADED";
            else if(name.EndsWith(".presence")){value=presence[row];status=value is null?"unknown":"known";reason=presenceReason[row];}
            else if(name.EndsWith(".seconds")&&presence[row]==false)reason="NOT_APPLICABLE_ABSENT";
            else {
                (status,value,reason)=Parse(name,token);
                if(status=="known"&&value is int){
                    if(meta[index*12+1]!=0)(status,value,reason)=("unknown",null,"NUMERIC_GLYPH_UNAVAILABLE");
                    else if(meta[index*12+4]!=0)(status,value,reason)=("unknown",null,"NUMERIC_GLYPH_TOUCHES_BOUNDARY");
                    else if(meta[index*12+3]!=token.Text.Length)(status,value,reason)=("unknown",null,"NUMERIC_CHARACTER_COUNT_MISMATCH");
                }
            }
            facts.Add(new(name,scope,status,status=="known"?value:null,reason,token.Text,token.Confidence));
        }
        return new(facts.ToArray(),geometry,global.ToArray(),timer.Elapsed.TotalMilliseconds,traces.ToArray());
    }
    internal static bool MaskCandidate(string cell,int mode,ReadToken token,ReadToken? native,int[] meta,int index) {
        int o=index*12;
        bool a5=cell=="A5_value"&&Regex.IsMatch(token.Text,@"^[0-9]{2}$");
        if(token.Confidence>=.85||meta[o]!=0||meta[o+1]!=0||meta[o+3]!=(a5?2:1)||meta[o+4]!=0)return false;
        bool allowed=a5||(cell=="A2_chg"?token.Text is "0" or "1" or "2":EffectRows.Any(row=>cell==row+"_value")&&token.Text=="0");
        if(!allowed)return false;
        return mode==1?cell!="A2_chg":mode==0&&meta[o+2]==0&&native is not null&&native.Text==token.Text&&native.Confidence<.85;
    }
    ReadResult Failed(Geometry g,string reason,double ms)=>new(layout.GetProperty("fields").EnumerateObject().Select(f=>new Fact(f.Name,f.Value.GetProperty("scope").GetString()!,"unknown",null,reason,"",null)).ToArray(),g,new[]{reason},ms);
    internal static (string,object?,string) Parse(string key,ReadToken token) {
        string text=token.Text;if(token.Confidence<.85)return("unknown",null,"OCR_LOW_CONFIDENCE");
        if(text is "?" or "!" or "~")return("unknown",null,"VISIBLE_ERROR_TOKEN");
        if(key=="C1.target_context")return text=="NT"?("known","no_target","VISIBLE_NT"):("unknown",null,"TARGET_IDENTITY_NOT_PROVIDED");
        if(key=="C1.hp_percent"&&text=="NT")return("unknown",null,"NOT_APPLICABLE_NO_TARGET");
        string[] allowed=key.EndsWith(".display")||key=="A2.recharge_display"?new[]{"OK","NA","—","-"}:key=="A2.charges"?new[]{"NA","-"}:key=="A7.ready"?new[]{"OK","—","-"}:key=="A7.uses"?new[]{"—","-"}:Array.Empty<string>();
        if(allowed.Contains(text))return("known",text,"VISIBLE_TOKEN");
        if(Regex.IsMatch(text,@"^[0-9]+$")&&int.TryParse(text,out int n)){
            if(key=="A7.ready")return("unknown",null,"UNSUPPORTED_RDY_TOKEN");
            if(key=="C1.hp_percent"&&n>100)return("unknown",null,"PERCENT_OUT_OF_RANGE");
            if(key=="A2.charges"&&n>2)return("unknown",null,"CHARGES_OUT_OF_RANGE");
            return("known",n,"VISIBLE_INTEGER");
        }return("unknown",null,"OCR_UNSUPPORTED_OR_EMPTY_TOKEN");
    }
    public void Dispose(){ocr.Dispose();jobs.Dispose();regionOutput.Dispose();band.Dispose();scratch.Dispose();images.Dispose();metadata.Dispose();refPixels.Dispose();refSpecs.Dispose();templateOutput.Dispose();}
}
