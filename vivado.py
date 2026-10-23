"""Optional installed Vivado XSim testbench runner; never a bundled Vivado install."""
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile


def discover(configured=None):
    candidates = []
    if configured:
        p=Path(str(configured).strip('"'))
        candidates += [p,p/'bin']
    for name in ('VIVADO_PATH','XILINX_VIVADO'):
        value = os.environ.get(name)
        if value:
            p=Path(value.strip('"'))
            candidates += [p, p/'bin']
    found=shutil.which('xvhdl') or shutil.which('xvhdl.bat')
    if found:
        candidates.append(Path(found).parent)
    if os.name=='nt':
        for root in (Path('C:/Xilinx/Vivado'),Path('C:/AMDDesignTools/Vivado'),Path('C:/AMD/Vivado')):
            if root.is_dir():
                candidates += [p/'bin' for p in sorted(root.iterdir(),reverse=True) if p.is_dir()]
        root=Path('C:/AMDDesignTools')
        if root.is_dir():
            candidates += [p/'Vivado/bin' for p in sorted(root.iterdir(),reverse=True) if p.is_dir()]
    for folder in (candidates[:2] if configured else candidates):
        tools={}
        for tool in ('xvhdl','xelab','xsim'):
            for suffix in (('.bat','.exe','') if os.name=='nt' else ('','.exe')):
                path=folder/(tool+suffix)
                if path.is_file():
                    tools[tool]=str(path.resolve())
                    break
        if len(tools)==3:
            return tools
    raise ValueError('Vivado XSim was not found. Set VIVADO_PATH to your installed Vivado folder or bin folder, then restart Nexys Lab. Vivado is installed separately; live Board mode currently uses GHDL.')


def status(configured=None):
    try:
        discover(configured)
        return {'available':True,'engine':'Vivado XSim','mode':'testbench','validated':False,
                'note':'Tools detected. Compile/run a testbench to validate this installation.'}
    except (ValueError,OSError) as exc:
        return {'available':False,'engine':'Vivado XSim','mode':'testbench','error':str(exc)}


def command(tool,args):
    if Path(tool).suffix.lower() in ('.bat','.cmd'):
        # Batch wrappers set Vivado's DLL environment. Reject shell-expanding
        # characters rather than interpreting any source/generic text as code.
        if any(re.search(r'[%!^&|<>"\r\n]',str(token)) for token in [tool,*args]):
            raise ValueError('Vivado batch paths/arguments cannot contain shell metacharacters. Use a plain installation path and integer/identifier generic values.')
        line='call "'+tool+'" '+' '.join('"'+str(arg)+'"' for arg in args)
        return [os.environ.get('COMSPEC','cmd.exe'),'/d','/s','/c',line]
    return [tool,*args]


def execute(tool,args,cwd,timeout=90):
    kwargs={'cwd':cwd,'text':True,'encoding':'utf-8','errors':'replace','stdout':subprocess.PIPE,'stderr':subprocess.STDOUT}
    if os.name=='nt':
        kwargs['creationflags']=subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session']=True
    proc=subprocess.Popen(command(tool,args),**kwargs)
    try:
        output,_=proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
        proc.kill()
        output,_=proc.communicate()
        raise ValueError('Vivado command exceeded its time limit. Its process tree was stopped.\n'+output[-10000:])
    return proc.returncode,output


def run(data):
    files=data.get('files',{})
    if not isinstance(files,dict) or not 1<=len(files)<=40:
        raise ValueError('Supply 1–40 source files')
    for name,text in files.items():
        if not re.fullmatch(r'[\w.-]+\.(vhd|vhdl|xdc|txt)',name,re.I) or not isinstance(text,str):
            raise ValueError('Invalid source file name')
    top=data.get('top','')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',top):
        raise ValueError('Invalid top entity')
    duration=data.get('duration','2us')
    match=re.fullmatch(r'([1-9][0-9]{0,5})(ns|us|ms)',duration)
    if not match:
        raise ValueError('Duration must be a positive integer followed by ns, us or ms')
    overrides=[]
    for name,value in (data.get('generics') or {}).items():
        literal=str(value).lower() if isinstance(value,bool) else str(value)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name) or not re.fullmatch(r'-?\d+|[A-Za-z][A-Za-z0-9_]*',literal):
            raise ValueError('Vivado generic overrides currently accept integers, booleans and enum identifiers. Use a source testbench wrapper for string generics.')
        overrides += ['--generic_top',name+'='+literal]
    tools=discover(data.get('vivado_path'))
    logs=[]
    with tempfile.TemporaryDirectory(prefix='nexys-xsim-') as directory:
        root=Path(directory)
        pending=[]
        for name,text in files.items():
            (root/name).write_text(text,encoding='utf-8')
            if name.lower().endswith(('.vhd','.vhdl')):pending.append(name)
        def call(name,args):
            code,output=execute(tools[name],args,directory)
            log='$ '+name+' '+' '.join(args)+'\n'+output
            return code,log
        while pending:
            remaining,failed=[],[]
            for name in pending:
                code,log=call('xvhdl',['--2008','--work','work',name])
                if code: remaining.append(name);failed.append(log)
                else: logs.append(log)
            if len(remaining)==len(pending):
                return {'ok':False,'phase':'analysis','log':'\n'.join(logs+failed),'engine':'vivado'}
            pending=remaining
        code,log=call('xelab',['--relax','--debug','typical','-L','unisim','-L','unimacro','-L','secureip',*overrides,'work.'+top,'--snapshot','nexys_test'])
        logs.append(log)
        if code:return {'ok':False,'phase':'elaboration','log':'\n'.join(logs),'engine':'vivado'}
        script='open_vcd signals.vcd\nlog_vcd [get_objects -r /*]\nrun '+match[1]+' '+match[2]+'\nclose_vcd\nquit\n'
        (root/'run.tcl').write_text(script)
        code,log=call('xsim',['nexys_test','--tclbatch','run.tcl'])
        logs.append(log)
        failed_assertion=bool(re.search(r'(?:^|\n)\s*(?:Fatal|Failure|Error):|Severity:\s*(?:Failure|Fatal|Error)',log,re.I))
        path=root/'signals.vcd'
        if path.exists() and path.stat().st_size>12000000:
            raise ValueError('Waveform exceeds 12 MB. Shorten the testbench duration.')
        return {'ok':code==0 and not failed_assertion,'phase':'simulation','log':'\n'.join(logs),
                'engine':'vivado','board':False,'vcd':path.read_text(errors='replace') if path.exists() else ''}


def self_test(configured=None):
    source='''library ieee; use ieee.std_logic_1164.all;
entity nexys_engine_check is end;
architecture test of nexys_engine_check is
 signal clk:std_logic:='0'; signal count:integer:=0;
begin clk<=not clk after 5 ns;
 process(clk) begin if rising_edge(clk) then count<=count+1; end if; end process;
 process begin wait for 41 ns;
 assert count=4 report "Clock execution failed" severity failure;
 report "NEXYS_XSIM_SELF_TEST_PASSED"; wait; end process;
end;'''
    result=run({'files':{'nexys_engine_check.vhd':source},'top':'nexys_engine_check','duration':'50ns','vivado_path':configured})
    result['ok']=result['ok'] and 'NEXYS_XSIM_SELF_TEST_PASSED' in result['log']
    return result
