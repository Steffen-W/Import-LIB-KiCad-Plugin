Assembles KiCad "legacy" format component libraries from downloaded
[Octopart](https://octopart.com/), [Samacsys](https://componentsearchengine.com/), [Ultralibrarian](https://app.ultralibrarian.com/search) and [Snapeda](https://www.snapeda.com/home/) zipfiles. 

Octopart and Samacsys still need updating, though several UltraLibrarian and Snapeda components have been tested and working. Major to-dos are listed in issues. Any help on these is apprecaited and collaboration via forking and PRs is appreciated. 

A very basic 3D model integration has been implemented to extract the 3D model, and inject a reference to this in the footprint. The main issue here is there is no gaurantee for the correct orientation, so some manual rotating/offset adjustments are typically necessary. Any FreeCAD scripting wizards willing to help automate that somehow would be greatly apprecaited. 

* Currently the document is still being edited

# Warranty
**None. Zero. Zilch. Use at your own risk, and please be sure to use git or some other means of backing up/reverting changes caused by this script. This script will modify existing lib, dcm, footprint or 3D model files. It is your responsiblity to back them up or have a way to revert changes should you inadvertantly mess something up using this tool** 

Umgebungsvarioablen
KICAD_3RD_PARTY ~/KiCad

Symbol:
1	1	Samacsys	${KICAD_3RD_PARTY}/Samacsys.lib	Legacy		
1	1	Snapeda	${KICAD_3RD_PARTY}/Snapeda.lib	Legacy		
1	1	UltraLibrarian	${KICAD_3RD_PARTY}/UltraLibrarian.lib	Legacy		


Footprint
1	Samacsys	${KICAD_3RD_PARTY}/Samacsys.pretty	KiCad	
1	Snapeda	${KICAD_3RD_PARTY}/Snapeda.pretty	KiCad		
1	UltraLibrarian	${KICAD_3RD_PARTY}/UltraLibrarian.pretty	KiCad		
