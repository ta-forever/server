Creator	"yFiles"
Version	"2.18"
graph
[
	hierarchic	1
	label	"scenario_0.gml"
	directed	1
	node
	[
		id	0
		label	"Core Prime"
        map "[Pro] Core Prime Industrial Area"
        mod "tavmod"
        size 100
        score [
          Arm 0.5
          Core 100
        ]
        controlled_by "Core"
        capital_of "Core"
		graphics
		[
			x	273.784
			y	248.13599999999997
			w	30.0
			h	30.0
			type	"ellipse"
			raisedBorder	0
			fill	"#FFCC00"
			outline	"#000000"
		]
		LabelGraphics
		[
			text	"Core Prime"
			fontSize	12
			fontName	"Dialog"
			model	"null"
		]
	]
	node
	[
		id	1
		label	"Barathrum"
        map "[Pro] Lava Run"
        mod "tavmod"
        size 50
        score [
          Arm 0
          Core 50
        ]
        controlled_by "Core"
		graphics
		[
			x	183.55200000000002
			y	168.83999999999997
			w	30.0
			h	30.0
			type	"ellipse"
			raisedBorder	0
			fill	"#FFCC00"
			outline	"#000000"
		]
		LabelGraphics
		[
			text	"Barathrum"
			fontSize	12
			fontName	"Dialog"
			model	"null"
		]
	]
	node
	[
		id	2
		label	"Thalassean"
        map "[V] Crimson Bay"
        mod "taesc"
        size 50
        score [
          Arm 50
          Core 50
        ]
		graphics
		[
			x	125.06400000000002
			y	248.13599999999997
			w	30.0
			h	30.0
			type	"ellipse"
			raisedBorder	0
			fill	"#FFCC00"
			outline	"#000000"
		]
		LabelGraphics
		[
			text	"Thalassean"
			fontSize	12
			fontName	"Dialog"
			model	"null"
		]
	]
	node
	[
		id	3
		label	"Lusch"
        map "[V] Great Divide 3"
        mod "tatw"
        size 50
        score [
          Arm 0
          Core 50
        ]
        controlled_by "Core"
		graphics
		[
			x	266.10400000000004
			y	115.80000000000001
			w	30.0
			h	30.0
			type	"ellipse"
			raisedBorder	0
			fill	"#FFCC00"
			outline	"#000000"
		]
		LabelGraphics
		[
			text	"Lusch"
			fontSize	12
			fontName	"Dialog"
			model	"null"
		]
	]
	node
	[
		id	4
		label	"Rougpelt"
        map "[Pro] Red Planet"
        mod "tatw"
        size 50
        score [
          Arm 50
          Core 50
        ]
		graphics
		[
			x	163.44
			y	15.0
			w	30.0
			h	30.0
			type	"ellipse"
			raisedBorder	0
			fill	"#FFCC00"
			outline	"#000000"
		]
		LabelGraphics
		[
			text	"Rougpelt"
			fontSize	12
			fontName	"Dialog"
			model	"null"
		]
	]
	node
	[
		id	5
		label	"Gelidus"
        map "[V] Winter Showdown"
        mod "tavmod"
        size 50
        score [
          Arm 50
          Core 0
        ]
        controlled_by "Arm"
		graphics
		[
			x	5.52800000000002
			y	163.488
			w	30.0
			h	30.0
			type	"ellipse"
			raisedBorder	0
			fill	"#FFCC00"
			outline	"#000000"
		]
		LabelGraphics
		[
			text	"Gelidus"
			fontSize	12
			fontName	"Dialog"
			model	"null"
		]
	]
	node
	[
		id	6
		label	"Dump"
        map "[Pro] Comet Catcher"
        mod "tavmod"
        size 50
        score [
          Arm 50
          Core 50
        ]
		graphics
		[
			x	101.0
			y	103.0
			w	30.0
			h	30.0
			type	"ellipse"
			raisedBorder	0
			fill	"#FFCC00"
			outline	"#000000"
		]
		LabelGraphics
		[
			text	"Dump"
			fontSize	12
			fontName	"Dialog"
			model	"null"
		]
	]
	node
	[
		id	7
		label	"Empyrrean"
        map "[Diox] Artificial Hills"
        mod "taesc"
        size 100
        score [
          Arm 100
          Core 0
        ]
        controlled_by "Arm"
        capital_of "Arm"
		graphics
		[
			x	1.9440000000000168
			y	15.0
			w	30.0
			h	30.0
			type	"ellipse"
			raisedBorder	0
			fill	"#FFCC00"
			outline	"#000000"
		]
		LabelGraphics
		[
			text	"Empyrrean"
			fontSize	12
			fontName	"Dialog"
			model	"null"
		]
	]
	edge
	[
		source	0
		target	1
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	0
		target	2
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	0
		target	3
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	2
		target	5
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	1
		target	6
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	3
		target	4
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	5
		target	7
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	6
		target	7
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	4
		target	7
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	2
		target	6
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	4
		target	1
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	1
		target	5
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
	edge
	[
		source	6
		target	3
		graphics
		[
			fill	"#000000"
			targetArrow	"standard"
		]
	]
]
