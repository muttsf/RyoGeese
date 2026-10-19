namespace GpuDash;
internal static class PackagePaths
{
    internal static string Root => Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,"..",".."));
    internal static string Reader => Path.Combine(Root,"reader");
    internal static string UserCache => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"RyoGeese","cache");
    internal static string FileIn(string root,string relative)
    {
        if(Path.IsPathRooted(relative))throw new InvalidOperationException("PACKAGE_ABSOLUTE_PATH");
        string parent=Path.GetFullPath(root)+Path.DirectorySeparatorChar;
        string file=Path.GetFullPath(Path.Combine(parent,relative));
        if(!file.StartsWith(parent,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("PACKAGE_PATH_OUTSIDE");
        return file;
    }
}
