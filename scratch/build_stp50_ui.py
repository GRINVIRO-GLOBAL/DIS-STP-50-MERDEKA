import os
import xml.etree.ElementTree as ET

def create_full_stp50_ui():
    ui_source_path = r"c:\Users\syari\OneDrive\Documents - Copy\Documents\DIS-HMI\[Project] Merdeka Copper Gold\STP 50\STP50.ui"
    tree = ET.parse(ui_source_path)
    root = tree.getroot()

    # Find ProcessFlow widget
    process_flow = next(w for w in root.iter("widget") if w.attrib.get("name") == "ProcessFlow")
    
    # Keep the 4 control buttons from right side
    keep_widgets = ["btn_alarm", "btn_estop", "btn_auto", "btn_manual"]
    existing_buttons = {}
    for c in list(process_flow):
        if c.attrib.get("name") in keep_widgets:
            existing_buttons[c.attrib.get("name")] = c
            
    # Clear children of ProcessFlow
    for c in list(process_flow):
        process_flow.remove(c)
        
    # Helper to add widget
    def add_widget(cls, name, x, y, w, h, stylesheet="", text="", pixmap="", icon="", icon_size=None, tooltip="", alignment=None, toolbutton_style=None):
        widget = ET.SubElement(process_flow, "widget", {"class": cls, "name": name})
        geom = ET.SubElement(widget, "property", {"name": "geometry"})
        rect = ET.SubElement(geom, "rect")
        ET.SubElement(rect, "x").text = str(x)
        ET.SubElement(rect, "y").text = str(y)
        ET.SubElement(rect, "width").text = str(w)
        ET.SubElement(rect, "height").text = str(h)
        
        if stylesheet:
            prop = ET.SubElement(widget, "property", {"name": "styleSheet"})
            ET.SubElement(prop, "string", {"notr": "true"}).text = stylesheet
            
        if text:
            prop = ET.SubElement(widget, "property", {"name": "text"})
            ET.SubElement(prop, "string").text = text
            
        if pixmap:
            prop = ET.SubElement(widget, "property", {"name": "pixmap"})
            ET.SubElement(prop, "pixmap", {"resource": "res_fix.qrc"}).text = pixmap
            prop_sc = ET.SubElement(widget, "property", {"name": "scaledContents"})
            ET.SubElement(prop_sc, "bool").text = "true"
            
        if icon:
            prop = ET.SubElement(widget, "property", {"name": "icon"})
            iconset = ET.SubElement(prop, "iconset", {"resource": "res_fix.qrc"})
            ET.SubElement(iconset, "normaloff").text = icon
            iconset.text = icon
            if icon_size:
                prop_is = ET.SubElement(widget, "property", {"name": "iconSize"})
                sz = ET.SubElement(prop_is, "size")
                ET.SubElement(sz, "width").text = str(icon_size[0])
                ET.SubElement(sz, "height").text = str(icon_size[1])
                
        if tooltip:
            prop = ET.SubElement(widget, "property", {"name": "toolTip"})
            ET.SubElement(prop, "string").text = tooltip
            
        if alignment:
            prop = ET.SubElement(widget, "property", {"name": "alignment"})
            ET.SubElement(prop, "set").text = alignment
            
        if toolbutton_style:
            prop = ET.SubElement(widget, "property", {"name": "toolButtonStyle"})
            ET.SubElement(prop, "enum").text = toolbutton_style
            
        if cls == "QToolButton":
            prop = ET.SubElement(widget, "property", {"name": "autoRaise"})
            ET.SubElement(prop, "bool").text = "true"
            prop_cur = ET.SubElement(widget, "property", {"name": "cursor"})
            ET.SubElement(prop_cur, "cursorShape").text = "PointingHandCursor"
            
        return widget

    # Standard pipe & fitting style
    P_STYLE = "background-color: transparent; border: none;"
    
    # 1. Background frame
    add_widget("QFrame", "bg_frame", 0, 0, 1050, 580, "background-color: #f8fafc; border: 1px solid #dcdfe6; border-radius: 8px;")

    # -------------------------------------------------------------
    # 2. THE 5 HORIZONTAL TANKS AT THE BOTTOM (y = 318 to 540)
    # -------------------------------------------------------------
    
    # --- TANK 1: TK-01 (INLET TANK) ---
    add_widget("QLabel", "title_TK01", 15, 318, 165, 22, 
               "background-color: #1a365d; color: white; font-weight: bold; font-size: 11px; qproperty-alignment: AlignCenter; border-radius: 4px;", 
               "TK-01 (INLET TANK)")
    # Base Tank graphic
    add_widget("QLabel", "LBL_inlet", 15, 360, 165, 175, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Inlet tank.png")
    # Water graphic
    add_widget("QLabel", "label_Inletwater", 20, 385, 155, 145, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Inlet tank (Water).png")
    # Animated water mask
    add_widget("QLabel", "label_Inletwater_2", 20, 385, 155, 145, "background-color: #f8fafc; border-bottom: 2px solid #2980b9;")
    # Level Switch LS-101
    add_widget("QLabel", "lbl_LS_101", 65, 345, 26, 38, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Level Switch.png", tooltip="LS-101: Inlet Level Switch")
    add_widget("QLabel", "lbl_tag_LS101", 95, 345, 45, 14, "color: #7f8c8d; font-weight: bold; font-size: 8px;", "LS-101")
    add_widget("QLabel", "txt_LS_101", 95, 359, 50, 16, "color: #2ecc71; font-weight: bold; font-size: 10px;", "HIGH")
    # Inlet Transfer Pumps TP-01A & TP-01B
    add_widget("QToolButton", "btn_TP_IN_A", 28, 455, 55, 70, "", "TP-01A", "", ":/FFI_icons/Icons/FFI_project/Motor.png", (42, 52), toolbutton_style="Qt::ToolButtonTextUnderIcon")
    add_widget("QToolButton", "btn_TP_IN_B", 95, 455, 55, 70, "", "TP-01B", "", ":/FFI_icons/Icons/FFI_project/Motor.png", (42, 52), toolbutton_style="Qt::ToolButtonTextUnderIcon")

    # --- TANK 2: EQ-01 (EQUALIZING TANK) ---
    add_widget("QLabel", "title_EQ01", 195, 318, 175, 22, 
               "background-color: #1a365d; color: white; font-weight: bold; font-size: 11px; qproperty-alignment: AlignCenter; border-radius: 4px;", 
               "EQ-01 (EQUALIZING)")
    # Base Tank graphic (U-shaped)
    add_widget("QLabel", "LBL_EQ_01", 195, 360, 175, 175, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Inlet tank.png")
    # Water graphic
    add_widget("QLabel", "label_EQ1water", 198, 385, 169, 145, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Inlet tank (Water).png")
    # Animated water mask
    add_widget("QLabel", "label_EQ1water_2", 198, 385, 169, 145, "background-color: #f8fafc; border-bottom: 2px solid #2980b9;")
    # Level Switch LS-102
    add_widget("QLabel", "lbl_LS_102", 225, 345, 26, 38, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Level Switch.png", tooltip="LS-102: EQ Level Switch")
    add_widget("QLabel", "lbl_tag_LS102", 255, 345, 45, 14, "color: #7f8c8d; font-weight: bold; font-size: 8px;", "LS-102")
    add_widget("QLabel", "txt_LS_102", 255, 359, 50, 16, "color: #2ecc71; font-weight: bold; font-size: 10px;", "HIGH")
    # Submersible Mixer SM-01
    add_widget("QToolButton", "btn_SM_01", 202, 465, 48, 60, "", "SM-01", "", ":/FFI_icons/Icons/FFI_project/Submersible mixer.png", (38, 42), toolbutton_style="Qt::ToolButtonTextUnderIcon")
    # Transfer Pumps TP-02A & TP-02B
    add_widget("QToolButton", "btn_TP_01A", 254, 455, 52, 70, "", "TP-02A", "", ":/FFI_icons/Icons/FFI_project/Motor.png", (40, 52), toolbutton_style="Qt::ToolButtonTextUnderIcon")
    add_widget("QToolButton", "btn_TP_01B", 310, 455, 52, 70, "", "TP-02B", "", ":/FFI_icons/Icons/FFI_project/Motor.png", (40, 52), toolbutton_style="Qt::ToolButtonTextUnderIcon")

    # --- TANK 3: AE-01 (AERATION TANK) ---
    add_widget("QLabel", "title_AE01", 385, 318, 175, 22, 
               "background-color: #1a365d; color: white; font-weight: bold; font-size: 11px; qproperty-alignment: AlignCenter; border-radius: 4px;", 
               "AE-01 (AERATION)")
    # Base Tank graphic
    add_widget("QLabel", "LBL_AE_01", 385, 360, 175, 175, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/AE-01.png")
    # Water graphic
    add_widget("QLabel", "label_AE1water", 388, 385, 169, 145, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/AE-01 (Water).png")
    # Animated water mask
    add_widget("QLabel", "label_AE1water2", 388, 385, 169, 145, "background-color: #f8fafc; border-bottom: 2px solid #2980b9;")
    # Aeration Diffuser
    add_widget("QFrame", "diffuser_AE01", 400, 522, 145, 8, "background-color: #f39c12; border: 1px solid #d68910; border-radius: 2px;")
    # DO Sensor Probe & Badge
    add_widget("QLabel", "lbl_DO_101", 420, 345, 22, 38, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Level Transmitter.png", tooltip="DO-101: Dissolved Oxygen Sensor")
    add_widget("QLabel", "lbl_tag_DO101", 448, 345, 50, 14, "color: #8e44ad; font-weight: bold; font-size: 8px;", "DO-101")
    add_widget("QLabel", "flow_DO101", 445, 359, 75, 18, 
               "background-color: #2c3e50; color: #00ffcc; font-weight: bold; font-size: 10px; border: 1px solid #34495e; border-radius: 3px; qproperty-alignment: AlignCenter;", 
               "0.80 mg/L")

    # --- TANK 4: MBR-01 (MEMBRANE TANK) ---
    add_widget("QLabel", "title_MBR01", 575, 318, 185, 22, 
               "background-color: #1a365d; color: white; font-weight: bold; font-size: 11px; qproperty-alignment: AlignCenter; border-radius: 4px;", 
               "MBR-01 (MEMBRANE)")
    # Base Tank graphic
    add_widget("QLabel", "LBL_MBR_01", 575, 360, 185, 175, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/AE-01.png")
    # Water graphic
    add_widget("QLabel", "label_mbrWater", 578, 385, 179, 145, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/AE-01 (Water).png")
    # Animated water mask
    add_widget("QLabel", "label_mbrwater2", 578, 385, 179, 145, "background-color: #f8fafc; border-bottom: 2px solid #2980b9;")
    # MBR Membrane Cassette
    add_widget("QLabel", "lbl_mbr_cassette", 585, 415, 58, 100, 
               "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a252f, stop:0.2 #2c3e50, stop:0.4 #1a252f, stop:0.6 #2c3e50, stop:0.8 #1a252f, stop:1 #2c3e50); border: 2px solid #1c2833; border-radius: 4px;", "")
    # Diffuser underneath cassette
    add_widget("QFrame", "diffuser_MBR01", 585, 522, 58, 8, "background-color: #f39c12; border: 1px solid #d68910; border-radius: 2px;")
    # Level Transmitter LT-101
    add_widget("QLabel", "lbl_LT_101", 605, 345, 16, 42, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Level Transmitter.png", tooltip="LT-101: MBR Tank Level")
    add_widget("QLabel", "lbl_tag_LT101", 628, 345, 45, 14, "color: #d35400; font-weight: bold; font-size: 8px;", "LT-101")
    add_widget("QLabel", "flow_LT101", 625, 359, 65, 18, 
               "background-color: #2c3e50; color: #00ffcc; font-weight: bold; font-size: 10px; border: 1px solid #34495e; border-radius: 3px; qproperty-alignment: AlignCenter;", 
               "1.85 m")
    # RAS Sludge Return Pumps TP-05A & TP-05B
    add_widget("QToolButton", "btn_TP_02A", 652, 455, 52, 70, "", "TP-05A", "", ":/FFI_icons/Icons/FFI_project/Motor.png", (40, 52), toolbutton_style="Qt::ToolButtonTextUnderIcon")
    add_widget("QToolButton", "btn_TP_02B", 708, 455, 52, 70, "", "TP-05B", "", ":/FFI_icons/Icons/FFI_project/Motor.png", (40, 52), toolbutton_style="Qt::ToolButtonTextUnderIcon")

    # --- TANK 5: TK-02 (TREATED WATER TANK) ---
    add_widget("QLabel", "title_TK02", 780, 318, 155, 22, 
               "background-color: #1a365d; color: white; font-weight: bold; font-size: 11px; qproperty-alignment: AlignCenter; border-radius: 4px;", 
               "TK-02 (TREATED WATER)")
    # 3D Tank graphic
    add_widget("QLabel", "LBL_TK_01", 790, 360, 135, 175, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/TK-01.png")
    # Water graphic
    add_widget("QLabel", "label_tank1water", 808, 385, 100, 145, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/TK-01 (water).png")
    # Animated water mask
    add_widget("QLabel", "label_tankwater2", 808, 385, 100, 145, "background-color: #f8fafc; border-bottom: 2px solid #27ae60;")
    # Level Switch LS-103
    add_widget("QLabel", "lbl_LS_103", 830, 340, 26, 38, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Level Switch.png", tooltip="LS-103: Permeate Tank Level Switch")
    add_widget("QLabel", "lbl_tag_LS103", 860, 340, 45, 14, "color: #7f8c8d; font-weight: bold; font-size: 8px;", "LS-103")
    add_widget("QLabel", "txt_LS_103", 860, 354, 50, 16, "color: #2ecc71; font-weight: bold; font-size: 10px;", "HIGH")

    # -------------------------------------------------------------
    # 3. OVERHEAD EQUIPMENT STATIONS (y = 20 to 280)
    # -------------------------------------------------------------
    
    # Station A: Air Blowers BL-01A & BL-01B (DOL)
    add_widget("QFrame", "box_BL01", 240, 25, 205, 115, "background-color: #ffffff; border: 2px dashed #f39c12; border-radius: 6px;")
    add_widget("QLabel", "title_BL01", 245, 30, 195, 16, "color: #d68910; font-weight: bold; font-size: 10px; qproperty-alignment: AlignCenter;", "BL-01A/B AIR BLOWERS (DOL)")
    add_widget("QToolButton", "btn_BL_01A", 246, 50, 88, 38, "font-weight: bold; font-size: 10px;", "BL-01A", "", ":/FFI_icons/Icons/FFI_project/Air blower.png", (38, 28), toolbutton_style="Qt::ToolButtonTextBesideIcon")
    add_widget("QToolButton", "btn_BL_01B", 246, 95, 88, 38, "font-weight: bold; font-size: 10px;", "BL-01B", "", ":/FFI_icons/Icons/FFI_project/Air blower.png", (38, 28), toolbutton_style="Qt::ToolButtonTextBesideIcon")
    # Blower discharge valves
    add_widget("QLabel", "v_chk_bla", 336, 58, 26, 24, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve.png")
    add_widget("QLabel", "v_bf_bla", 365, 58, 26, 24, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Butterfly valve (Opened).png")
    add_widget("QLabel", "v_chk_blb", 336, 103, 26, 24, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve.png")
    add_widget("QLabel", "v_bf_blb", 365, 103, 26, 24, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Butterfly valve (Opened).png")
    # Yellow junctions & headers inside blower station
    add_widget("QLabel", "j_bl_t", 395, 58, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/T pipe junction (yellow).png")
    add_widget("QLabel", "p_bl_mid_v", 398, 79, 16, 25, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe (yellow) V.png")
    add_widget("QLabel", "j_bl_l", 395, 103, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction (yellow) 90.png")
    add_widget("QLabel", "p_bl_out_h", 416, 61, 28, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe (yellow).png")

    # Yellow Air Piping to Aeration & MBR Diffusers
    add_widget("QLabel", "gauge_air", 425, 32, 22, 26, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pressure Gauge.png")
    add_widget("QLabel", "p_air_h1", 443, 61, 25, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe (yellow).png")
    add_widget("QLabel", "j_air_ae_t", 467, 58, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/T pipe junction (yellow) up.png")
    # Downcomer yellow pipe into AE-01
    add_widget("QLabel", "p_air_ae_v1", 470, 79, 16, 90, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe (yellow) V.png")
    add_widget("QLabel", "p_air_ae_v2", 470, 168, 16, 90, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe (yellow) V.png")
    add_widget("QLabel", "p_air_ae_v3", 470, 257, 16, 90, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe (yellow) V.png")
    add_widget("QLabel", "p_air_ae_v4", 470, 346, 16, 175, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe (yellow) V.png")
    # Continuing horizontal yellow line to MBR-01
    add_widget("QLabel", "p_air_mbr_h1", 488, 61, 115, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe (yellow).png")
    add_widget("QLabel", "j_air_mbr_l", 602, 58, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction (yellow) 90.png")
    add_widget("QLabel", "p_air_mbr_v1", 605, 79, 16, 90, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe (yellow) V.png")
    add_widget("QLabel", "p_air_mbr_v2", 605, 168, 16, 90, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe (yellow) V.png")
    add_widget("QLabel", "p_air_mbr_v3", 605, 257, 16, 90, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe (yellow) V.png")
    add_widget("QLabel", "p_air_mbr_v4", 605, 346, 16, 175, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe (yellow) V.png")

    # Station B: Permeate Suction Manifold TP-04A & TP-04B (VFD)
    add_widget("QFrame", "box_TP04", 515, 150, 235, 125, "background-color: #ffffff; border: 1px solid #3498db; border-radius: 6px;")
    add_widget("QLabel", "title_TP04", 520, 154, 225, 16, "color: #2980b9; font-weight: bold; font-size: 10px; qproperty-alignment: AlignCenter;", "PERMEATE SUCTION (VFD)")
    # Permeate Auto Valve AV-101
    add_widget("QToolButton", "btn_AV101", 572, 192, 45, 35, "", "AV-101", "", ":/FFI_icons/Icons/FFI_project/Auto valve (Rev1).png", (45, 32))
    # Pressure Transmitter PT-101
    add_widget("QLabel", "lbl_PT101", 528, 175, 24, 35, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/PT with bar.png", tooltip="PT-101: MBR Suction Pressure")
    add_widget("QLabel", "lbl_tag_PT101", 522, 212, 45, 12, "color: #c0392b; font-weight: bold; font-size: 8px; qproperty-alignment: AlignCenter;", "PT-101")
    add_widget("QLabel", "flow_PT101", 518, 225, 68, 18, 
               "background-color: #2c3e50; color: #00ffcc; font-weight: bold; font-size: 10px; border: 1px solid #34495e; border-radius: 3px; qproperty-alignment: AlignCenter;", 
               "-0.15 bar")
    # Pumps TP-04A and TP-04B
    add_widget("QToolButton", "btn_TP_03A", 632, 172, 50, 36, "", "TP-04A", "", ":/FFI_icons/Icons/FFI_project/Motor H.png", (42, 55))
    add_widget("QToolButton", "btn_TP_03B", 632, 228, 50, 36, "", "TP-04B", "", ":/FFI_icons/Icons/FFI_project/Motor 90.png", (42, 55))
    # Permeate valves & check valves
    add_widget("QLabel", "v_chk_04a", 685, 178, 26, 24, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve.png")
    add_widget("QLabel", "v_chk_04b", 685, 234, 26, 24, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve.png")
    # Flow Transmitter FT-102 & Badge
    add_widget("QLabel", "lbl_FT102", 720, 182, 26, 35, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Flow Transmitter.png", tooltip="FT-102: Permeate Flow Transmitter")
    add_widget("QLabel", "lbl_tag_FT102", 715, 218, 45, 12, "color: #2980b9; font-weight: bold; font-size: 8px; qproperty-alignment: AlignCenter;", "FT-102")
    add_widget("QLabel", "flow_FT102", 712, 232, 70, 18, 
               "background-color: #2c3e50; color: #00ffcc; font-weight: bold; font-size: 10px; border: 1px solid #34495e; border-radius: 3px; qproperty-alignment: AlignCenter;", 
               "0.00 m3/h")
    # Permeate line from MBR cassette to Permeate box
    add_widget("QLabel", "p_perm_rise1", 588, 274, 16, 146, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")
    add_widget("QLabel", "j_perm_l1", 585, 200, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 180.png")
    add_widget("QLabel", "p_perm_h_in", 552, 203, 34, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")
    # Header splitting inside box
    add_widget("QLabel", "j_perm_split", 616, 200, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/T pipe junction 90.png")
    add_widget("QLabel", "p_perm_up", 619, 182, 16, 19, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe V.png")
    add_widget("QLabel", "j_perm_a", 616, 169, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction.png")
    add_widget("QLabel", "p_perm_dn", 619, 221, 16, 19, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe V.png")
    add_widget("QLabel", "j_perm_b", 616, 239, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 180.png")
    # Merging header
    add_widget("QLabel", "j_perm_merge", 708, 200, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/T pipe junction 270.png")
    add_widget("QLabel", "p_perm_out", 745, 203, 40, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")
    add_widget("QLabel", "j_perm_drop", 784, 200, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 90.png")
    add_widget("QLabel", "p_perm_tk2_down", 787, 221, 16, 140, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")

    # Station C: Backwash Manifold TP-03 (VFD-103)
    add_widget("QFrame", "box_TP03", 645, 25, 165, 115, "background-color: #ffffff; border: 1px solid #27ae60; border-radius: 6px;")
    add_widget("QLabel", "title_TP03", 650, 30, 155, 16, "color: #27ae60; font-weight: bold; font-size: 10px; qproperty-alignment: AlignCenter;", "BACKWASH (VFD-103)")
    add_widget("QToolButton", "btn_TP_04", 735, 55, 52, 45, "", "TP-03", "", ":/FFI_icons/Icons/FFI_project/Motor H.png", (42, 55))
    add_widget("QLabel", "v_chk_bw", 705, 68, 26, 24, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve.png")
    add_widget("QToolButton", "btn_AV102", 662, 62, 40, 35, "", "AV-102", "", ":/FFI_icons/Icons/FFI_project/Auto valve (Rev1).png", (40, 32))
    # Flow Transmitter FT-103 & Badge
    add_widget("QLabel", "lbl_FT103", 625, 48, 26, 35, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Flow Transmitter.png", tooltip="FT-103: Backwash Flow Transmitter")
    add_widget("QLabel", "lbl_tag_FT103", 620, 84, 45, 12, "color: #27ae60; font-weight: bold; font-size: 8px; qproperty-alignment: AlignCenter;", "FT-103")
    add_widget("QLabel", "flow_FT103", 615, 98, 70, 18, 
               "background-color: #2c3e50; color: #00ffcc; font-weight: bold; font-size: 10px; border: 1px solid #34495e; border-radius: 3px; qproperty-alignment: AlignCenter;", 
               "0.00 m3/h")
    # Backwash suction from TK-02
    add_widget("QLabel", "p_bw_rise1", 825, 92, 16, 270, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")
    add_widget("QLabel", "j_bw_top", 822, 70, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction.png")
    add_widget("QLabel", "p_bw_h1", 786, 73, 37, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")
    # Backwash discharge dropping into MBR cassette
    add_widget("QLabel", "j_bw_drop", 612, 70, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 180.png")
    add_widget("QLabel", "p_bw_down_mbr", 615, 91, 16, 329, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")

    # Station D: CEB Chemical Dosing DP-01 & JC-01
    add_widget("QFrame", "box_DP01", 830, 25, 110, 115, "background-color: #ffffff; border: 1px dashed #e67e22; border-radius: 6px;")
    add_widget("QLabel", "title_DP01", 835, 30, 100, 16, "color: #d35400; font-weight: bold; font-size: 10px; qproperty-alignment: AlignCenter;", "CEB DOSING")
    add_widget("QLabel", "LBL_JC_01", 895, 52, 35, 52, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Chemical dosing tank-rev.png")
    add_widget("QLabel", "lbl_tag_JC01", 895, 107, 35, 14, "color: #d35400; font-weight: bold; font-size: 8px; qproperty-alignment: AlignCenter;", "JC-01")
    add_widget("QToolButton", "btn_DP_01", 842, 55, 45, 45, "", "DP-01", "", ":/FFI_icons/Icons/FFI_project/1Motor.png", (55, 42))
    # Dosing pipe connecting into backwash line
    add_widget("QLabel", "p_dose_h", 814, 82, 30, 14, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")

    # -------------------------------------------------------------
    # 4. TRANSFER PIPING BETWEEN TANKS (3D Sprites, Valves, Gauges)
    # -------------------------------------------------------------
    
    # --- Line 1: Inlet Transfer (TK-01 -> EQ-01) ---
    # Riser from TP-01A
    add_widget("QLabel", "p_in_01a_v1", 47, 430, 16, 25, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe V.png")
    add_widget("QLabel", "v_chk_01a", 42, 403, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve V.png")
    add_widget("QLabel", "v_ball_01a", 42, 376, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Ball valve V.png")
    add_widget("QLabel", "p_in_01a_v2", 47, 319, 16, 58, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")
    add_widget("QLabel", "j_in_01a_l", 47, 298, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 180.png")
    # Riser from TP-01B
    add_widget("QLabel", "p_in_01b_v1", 112, 430, 16, 25, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe V.png")
    add_widget("QLabel", "v_chk_01b", 107, 403, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve V.png")
    add_widget("QLabel", "v_ball_01b", 107, 376, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Ball valve V.png")
    add_widget("QLabel", "p_in_01b_v2", 112, 319, 16, 58, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")
    add_widget("QLabel", "j_in_01b_t", 112, 298, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/T pipe junction 90.png")
    # Header between pumps
    add_widget("QLabel", "p_in_h1", 68, 301, 45, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")
    # Header continuing to FT-101 and EQ-01
    add_widget("QLabel", "gauge_in_pg", 135, 278, 22, 26, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pressure Gauge.png")
    add_widget("QLabel", "p_in_h2", 133, 301, 30, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")
    add_widget("QLabel", "lbl_FT101", 162, 280, 26, 35, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Flow Transmitter.png", tooltip="FT-101: Inlet Flow Transmitter")
    add_widget("QLabel", "lbl_tag_FT101", 155, 248, 45, 12, "color: #2980b9; font-weight: bold; font-size: 8px; qproperty-alignment: AlignCenter;", "FT-101")
    add_widget("QLabel", "flow_FT101", 145, 261, 75, 18, 
               "background-color: #2c3e50; color: #00ffcc; font-weight: bold; font-size: 10px; border: 1px solid #34495e; border-radius: 3px; qproperty-alignment: AlignCenter;", 
               "0.00 m3/h")
    add_widget("QLabel", "p_in_h3", 187, 301, 35, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")
    add_widget("QLabel", "j_in_drop", 221, 298, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 90.png")
    add_widget("QLabel", "p_in_down_eq", 224, 319, 16, 75, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")

    # --- Line 2: Equalizing Transfer (EQ-01 -> AE-01) ---
    # Riser from TP-02A
    add_widget("QLabel", "p_eq_02a_v1", 270, 430, 16, 25, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe V.png")
    add_widget("QLabel", "v_chk_02a", 265, 403, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve V.png")
    add_widget("QLabel", "v_ball_02a", 265, 376, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Ball valve V.png")
    add_widget("QLabel", "p_eq_02a_v2", 270, 319, 16, 58, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")
    add_widget("QLabel", "j_eq_02a_l", 270, 298, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 180.png")
    # Riser from TP-02B
    add_widget("QLabel", "p_eq_02b_v1", 328, 430, 16, 25, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe V.png")
    add_widget("QLabel", "v_chk_02b", 323, 403, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve V.png")
    add_widget("QLabel", "v_ball_02b", 323, 376, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Ball valve V.png")
    add_widget("QLabel", "p_eq_02b_v2", 328, 319, 16, 58, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")
    add_widget("QLabel", "j_eq_02b_t", 328, 298, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/T pipe junction 90.png")
    # Header between pumps
    add_widget("QLabel", "p_eq_h1", 291, 301, 38, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")
    # Header continuing to AE-01
    add_widget("QLabel", "gauge_eq_pg", 355, 278, 22, 26, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pressure Gauge.png")
    add_widget("QLabel", "p_eq_h2", 349, 301, 60, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe.png")
    add_widget("QLabel", "j_eq_drop", 408, 298, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 90.png")
    add_widget("QLabel", "p_eq_down_ae", 411, 319, 16, 75, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")

    # --- Line 3: Gravity Overflow (AE-01 -> MBR-01) ---
    add_widget("QLabel", "p_overflow", 558, 395, 25, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")

    # --- Line 4: RAS Sludge Return (MBR-01 -> AE-01) ---
    # Riser from TP-05A
    add_widget("QLabel", "p_ras_05a_v1", 668, 430, 16, 25, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe V.png")
    add_widget("QLabel", "v_chk_05a", 663, 403, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve V.png")
    add_widget("QLabel", "v_ball_05a", 663, 376, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Ball valve V.png")
    add_widget("QLabel", "p_ras_05a_v2", 668, 319, 16, 58, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")
    add_widget("QLabel", "j_ras_05a_t", 668, 298, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/T pipe junction 90.png")
    # Riser from TP-05B
    add_widget("QLabel", "p_ras_05b_v1", 724, 430, 16, 25, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe V.png")
    add_widget("QLabel", "v_chk_05b", 719, 403, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Check valve V.png")
    add_widget("QLabel", "v_ball_05b", 719, 376, 26, 28, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Ball valve V.png")
    add_widget("QLabel", "p_ras_05b_v2", 724, 319, 16, 58, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")
    add_widget("QLabel", "j_ras_05b_l", 724, 298, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 90.png")
    # Header returning sludge back left into AE-01
    add_widget("QLabel", "p_ras_h1", 689, 301, 36, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Pipe.png")
    add_widget("QLabel", "p_ras_h2", 562, 301, 107, 16, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe.png")
    add_widget("QLabel", "j_ras_drop", 541, 298, 22, 22, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/L pipe junction 180.png")
    add_widget("QLabel", "p_ras_down_ae", 544, 319, 16, 75, P_STYLE, "", ":/FFI_icons/Icons/FFI_project/Long Pipe V.png")

    # Re-insert the 4 control buttons (ALARM, ESTOP, AUTO, MANUAL)
    for btn_name in keep_widgets:
        if btn_name in existing_buttons:
            process_flow.append(existing_buttons[btn_name])

    # Write out updated STP50.ui
    tree.write(ui_source_path, encoding="utf-8", xml_declaration=True)
    print("Successfully generated polished rich FFI STP50.ui!")

if __name__ == "__main__":
    create_full_stp50_ui()
