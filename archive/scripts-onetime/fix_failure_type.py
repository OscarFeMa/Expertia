with open("D:/proyectos/expertia/incubator-root/orchestrator.py", "r") as f:
    content = f.read()

old = "pkgs_saved == 0:\n                result['failure_type'] = 'system'"
new = "pkgs_saved == 0:\n                result['failure_type'] = 'knowledge'"

if old in content:
    content = content.replace(old, new)
    with open("D:/proyectos/expertia/incubator-root/orchestrator.py", "w") as f:
        f.write(content)
    print("Fixed!")
else:
    print("Not found")
    idx = content.find("pkgs_saved == 0")
    print(f"Found at: {idx}")
    print(content[idx:idx+100])