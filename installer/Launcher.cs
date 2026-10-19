// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 手电加鞭
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;

[assembly: AssemblyTitle("RyoGeese")]
[assembly: AssemblyProduct("RyoGeese")]
[assembly: AssemblyCompany("手电加鞭")]

internal static class Launcher {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    private static extern int MessageBox(IntPtr owner,string text,string title,uint flags);

    private static string Root() {
        string own=Path.GetDirectoryName(typeof(Launcher).Assembly.Location);
        string target=Path.Combine(own,"RyoGeese启动位置.txt");
        if(!File.Exists(target)) return own;
        if(new FileInfo(target).Length>4096) throw new IOException("启动位置文件无效。");
        string relative=File.ReadAllText(target,Encoding.UTF8).Trim();
        if(relative.Length==0 || Path.IsPathRooted(relative)) throw new IOException("启动位置必须是相对目录。");
        string root=Path.GetFullPath(Path.Combine(own,relative));
        if(!root.StartsWith(own+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))
            throw new IOException("启动位置不能超出软件目录。");
        return root;
    }

    private static string Escape(string value) {
        var text=new StringBuilder();
        foreach(char c in value) {
            if(c=='"' || c=='\\') text.Append('\\').Append(c);
            else if(c<32) text.Append("\\u").Append(((int)c).ToString("x4"));
            else text.Append(c);
        }
        return text.ToString();
    }

    private static void Report(Exception error) {
        try {
            string folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"RyoGeese","logs");
            Directory.CreateDirectory(folder);
            string stamp=DateTimeOffset.Now.ToString("yyyy-MM-dd_HH-mm-ss_ffffff");
            string file=Path.Combine(folder,"报错_"+stamp+"_"+Guid.NewGuid().ToString("N").Substring(0,8)+"_0001.txt");
            string message=error.Message; if(message.Length>8192)message=message.Substring(0,8192);
            File.WriteAllText(file,"{\"时间\":\""+DateTimeOffset.Now.ToString("o")+"\",\"kind\":\"LAUNCHER_ERROR\",\"message\":\""+Escape(message)+"\"}"+Environment.NewLine,new UTF8Encoding(false));
        } catch { }
        MessageBox(IntPtr.Zero,error.Message,"RyoGeese未能打开",0x10);
    }

    [STAThread]
    private static int Main(string[] args) {
        bool check=args.Length==1 && args[0]=="--check";
        try {
            string root=Root();
            string python=Path.Combine(root,"runtime","python","pythonw.exe");
            string entry=Path.Combine(root,"bootstrap.py");
            if(!File.Exists(python) || !File.Exists(entry)) throw new FileNotFoundException("没有找到软件运行文件，请保留完整的软件文件夹。");
            if(check)return 0;
            var start=new ProcessStartInfo(python,"-E -s -B \""+entry+"\"");
            start.WorkingDirectory=root;start.UseShellExecute=false;start.CreateNoWindow=true;
            start.WindowStyle=ProcessWindowStyle.Hidden;
            using(var process=Process.Start(start)) { if(process==null)throw new IOException("启动未成功，请重新打开软件。"); }
            return 0;
        } catch(Exception error) {
            if(!check)Report(error);
            return 2;
        }
    }
}
