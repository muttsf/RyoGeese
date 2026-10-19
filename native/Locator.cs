namespace GpuDash;

internal record Geometry(double Scale,double Left,double Top,string Variant,double Residual)
{
    internal int[] Pixels(double[] r) {
        int x=checked((int)Math.Round(Left+Scale*r[0])),y=checked((int)Math.Round(Top+Scale*(306-r[1]-r[3])));
        return new[]{x,y,checked((int)Math.Round(Left+Scale*(r[0]+r[2])))-x,checked((int)Math.Round(Top+Scale*(306-r[1])))-y};
    }
}
internal static class Locator
{
    internal static void ValidateInput(int w,int h,nuint bytes) {
        if(w<=0||h<=0||w>4096||h>2304||bytes<(nuint)(4L*w*h))throw new ArgumentException("LOCATOR_INPUT_BOUNDS");
    }
    internal static Geometry Find(KernelModule kernel,DeviceBuffer image,int w,int h) {
        ValidateInput(w,h,image.Bytes);
        // Scratch is startup/relocate-only and disposed before regular reading.
        using var parent=new DeviceBuffer(w*(long)h*4);
        using var stats=new DeviceBuffer(w*(long)h*20);
        using var candidates=new DeviceBuffer(416*5*8);
        using var counts=new DeviceBuffer(3*4);
        using var results=new DeviceBuffer(2*4,true);
        using var output=new DeviceBuffer(16*5*8,true);
        counts.Zero();results.Zero();
        kernel.Run("white_init",w*h,Cuda.Ptr(image.Pointer),(ulong)(w*h),Cuda.Ptr(parent.Pointer),Cuda.Ptr(stats.Pointer));
        kernel.Run("white_join",w*h,(ulong)w,(ulong)h,Cuda.Ptr(parent.Pointer));
        kernel.Run("white_stats",w*h,(ulong)w,(ulong)h,Cuda.Ptr(parent.Pointer),Cuda.Ptr(stats.Pointer));
        kernel.Run("marker_candidates",w*h,(ulong)(w*h),Cuda.Ptr(stats.Pointer),Cuda.Ptr(counts.Pointer),Cuda.Ptr(candidates.Pointer));
        kernel.Run("locate",4096,Cuda.Ptr(counts.Pointer),Cuda.Ptr(candidates.Pointer),(ulong)w,(ulong)h,Cuda.Ptr(results.Pointer),Cuda.Ptr(output.Pointer));
        var state=results.Metadata<int>(2);
        if(state[1]!=0)throw new InvalidOperationException("LOCATOR_CANDIDATE_OVERFLOW");
        if(state[0]==0)throw new InvalidOperationException("NO_UNIQUE_MARKERS");
        var values=output.Metadata<double>(state[0]*5);
        var all=Enumerable.Range(0,state[0]).Select(i=>new Geometry(values[5*i],values[5*i+1],values[5*i+2],values[5*i+3]==0?"D_VISIBLE":"D_HIDDEN",values[5*i+4]))
            .DistinctBy(g=>(Math.Round(g.Scale,2),Math.Round(g.Left,2),Math.Round(g.Top,2))).ToArray();
        if(all.Length!=1)throw new InvalidOperationException("NO_UNIQUE_MARKERS:"+all.Length);
        return all[0];
    }
}
