from pathlib import Path
import run


def test_reuses_existing_instance_without_starting_second_server(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run,"server_state",lambda:"stratix")
    opened=[]
    monkeypatch.setattr(run.webbrowser,"open",opened.append)
    assert run.main([])==0
    assert opened==[run.URL]
    assert Path.cwd()==run.ROOT


def test_other_program_on_port_is_not_stopped(monkeypatch):
    monkeypatch.setattr(run,"server_state",lambda:"occupied")
    assert run.main(["--check"])==1
