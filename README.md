# hass-hgl-to-yaml

Defines a grammar-based language for Home Assistant Automations and
convert those to native YAML for hass.

See the grammer in the hass-hgl-to-yaml.py source file.

And see the examples below (which go in a file with a .hgl extension)

```
# expands into two separate rules, one for each _ir sensor
when {pantry,kitchen}_ir is Normal for 3 minutes do turn_off(light.mh_m_*)

when pantry_ir and kitchen_ir is Normal for 3 minutes do turn_of(light.{pantry,kitchen}_ceiling)

when lock.mho_entry_door_lock is unlocked with *.method == "keypad" and *.code_id == "1" do vantage.call_task_vid(vid=5123)

when out_breezeway_ir is Violated when sensor.nighttime_dark_mode == "1.0" do turn_on(light.mh_out_breezeway_breezeway_cans)
     else Normal for 10 minutes do turn_off(*)

when bed_loft_idr is Violated
    do alarm_control_panel.elkm1_alarm_display_message(alarm_control_panel.area_002,line1="loft",line2="door opened",timeout=0,beep=1)
    else Normal do *(alarm_control_panel.area_002,line1="loft",line2="door closed",timeout=10,beep=0)

when doorbird_{driveway,office,pedestrian,mh_main,gh_main,mh_basement}_button_1 fires
    do play_doorbird_media(master_bath_display,loft_display,kitchen_max)

when EXITED_TALL do vantage.call_task_vid(vid=6123)

when EH_media_{pause,play,play_pause,volume_up,volume_down,channel_down} do media_player.media_*(entry_hall)

when HTTV_media_{all_off,all_on,all_on_hdmi1,all_hdmi1} do script.mh_b_vizio_tvs_*

when VACUUM_CLEAN_{nook,full_nook,great_room,kitchen,mud_room,pantry} do script.vacuum_*

sunrise ... solar_noon -01:00:00
  with cover.mh_m_great_room_upper_east
    start when sunny:
      cover.close_cover
    end:
      cover.open_cover

garden_speaker powered_by switch.ph_b_wb_{o4_garden_4,o9_sw_garden_9}

* off_at 23:45
```
