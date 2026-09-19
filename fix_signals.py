from pathlib import Path

p = Path("sumo/network.net.xml")
s = p.read_text()

for intersection in ["I1", "I4", "I5", "I8"]:
    start = s.find(f'<tlLogic id="{intersection}"')
    end = s.find("</tlLogic>", start) + len("</tlLogic>")

    if start == -1 or end == -1:
        print(f"{intersection}: NOT FOUND")
        continue

    new_block = f'''<tlLogic id="{intersection}" type="actuated" programID="0" offset="0">
        <phase duration="30" state="GrGr" minDur="10" maxDur="60"/>
        <phase duration="3" state="yryr"/>
        <phase duration="30" state="rGrG" minDur="10" maxDur="60"/>
        <phase duration="3" state="ryry"/>
    </tlLogic>'''

    s = s[:start] + new_block + s[end:]
    print(f"{intersection}: updated")

p.write_text(s)
print("DONE")
