# 개발용 Fieldeck 바로가기 만들기 (소스 폴더의 'Fieldeck (개발).lnk' + 시작 메뉴) — 설치본은 설치 프로그램이 만든다
# 바로가기에 앱 ID(Fieldeck.App, core/appinfo.py와 같은 값)를 넣어
# 작업 표시줄·시작 메뉴에 'Python' 대신 'Fieldeck' 이름과 아이콘이 나오게 한다.
# 실행: powershell -ExecutionPolicy Bypass -File tools\make_shortcuts.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$appId = "Fieldeck.App"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;

[ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr fd, uint fl);
    void GetIDList(out IntPtr p); void SetIDList(IntPtr p);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetHotkey(out short h); void SetHotkey(short h);
    void GetShowCmd(out int i); void SetShowCmd(int i);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c, out int i);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string s, int i);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string s, uint r);
    void Resolve(IntPtr h, uint f);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string s);
}

[ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPersistFile {
    void GetClassID(out Guid g); [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint m);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string f, bool r);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string f);
    void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string f);
}

[StructLayout(LayoutKind.Sequential, Pack = 4)]
struct PROPERTYKEY { public Guid fmtid; public uint pid; }

[StructLayout(LayoutKind.Explicit)]
struct PROPVARIANT { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; [FieldOffset(16)] public IntPtr p2; }

[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPropertyStore {
    void GetCount(out uint c); void GetAt(uint i, out PROPERTYKEY k);
    void GetValue(ref PROPERTYKEY k, out PROPVARIANT v);
    void SetValue(ref PROPERTYKEY k, ref PROPVARIANT v);
    void Commit();
}

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
class CShellLink { }

public static class RhShortcut {
    public static void Make(string lnk, string target, string args, string dir, string icon, string desc, string appId) {
        var link = (IShellLinkW)new CShellLink();
        link.SetPath(target);
        link.SetArguments(args);
        link.SetWorkingDirectory(dir);
        link.SetIconLocation(icon, 0);
        link.SetDescription(desc);
        var store = (IPropertyStore)link;
        var key = new PROPERTYKEY { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };   // System.AppUserModel.ID
        var pv = new PROPVARIANT { vt = 31, p = Marshal.StringToCoTaskMemUni(appId) };                     // VT_LPWSTR
        store.SetValue(ref key, ref pv);
        store.Commit();
        Marshal.FreeCoTaskMem(pv.p);
        ((IPersistFile)link).Save(lnk, true);
    }
}
"@

$target = Join-Path $root ".venv\Scripts\pythonw.exe"
$args_ = '"' + (Join-Path $root "main.py") + '"'
$icon = Join-Path $root "assets\app.ico"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Fieldeck (개발).lnk"
foreach ($lnk in @((Join-Path $root "Fieldeck (개발).lnk"), $startMenu)) {
    [RhShortcut]::Make($lnk, $target, $args_, $root, $icon, "Fieldeck (개발) - 원격 PC 다중 접속", $appId)
    Write-Output "만듦: $lnk"
}
