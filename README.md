# hass-hgl-to-yaml

## Overview 
Defines a grammar-based language for Home Assistant Automations and
convert those to native YAML for hass.

See the grammer in the hass-hgl-to-yaml.py source file. Various examples are below (which go in a file with a .hgl extension):

## Examples
```
# expands into two separate rules, one for each _ir sensor
when {pantry,kitchen}_ir is Normal for 3 minutes do turn_off(light.mh_m_*)

when pantry_ir and kitchen_ir is Normal for 3 minutes do turn_off(light.{pantry,kitchen}_ceiling)

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

## Comments

Comments start with "#" and continue to the end of line; they are ignored.

## Rule Types

There are three broad variety of sentences supported

1. "when" rules that trigger an action when something happens (state changes, mqtt message received, or event fired).

1. "power control" rules that state that a media device needs a switch powered on (generates rules to power that device on when the media device starts playing, and turn it off when idle/stopped.)

1. "time range" rules that manipulate the same devices at a start time and an end time.

The sentences all can specify actions and many can have conditions and support shell-like brace expansion.


### when - mqtt

```
when_mqtt: "when" mqtt_message [condition_clause] "do" action
```

### when - event fires
``` 
when_fires: "when" event "fires" condition_clause? "do" action
```

### when - state changes
```
when: "when" entity_state for_clause? condition_clause? "do" action else_clause?
```

### power control
```
power_control: ENTITY "powered_by" BRACE_EXPANDED_ENTITY
               | /*/ "off_at" time
```

There is also a special rule "* off_at TIME" that turns off at the specified time all the media devices controlled by other power_control rules in that same file.

### time range
```
time_range: "from" time "to" time with_clause start_clause end_clause
            | time "..." time with_clause start_clause end_clause
```

## Actions

Actions are specified as just the service name with optional parenthesis within which the entity_id is specified and/or additional name-value pairs for other data: fields. E.g.,

```
turn_off(light.some_light)
alarm_control_panel.elkm1_alarm_display_message(alarm_control_panel.area_002,line1="loft",line2="door opened",timeout=0,beep=1)
```

Actions can contain a "*" character which gets replaced with each comma-separated brace expansion from the left-hand-side.

## Conditions

Conditions check entity values and can use "and" and "or" for conjunctions and disjunctions.  The entity domain defaults to "sensor." if not specified. E.g.,

```
# triggers when both sensor.pantry_motion and sensor.kitchen_motion are in state "Normal"
pantry_motion and kitchen_motion is Normal
pantry_motion is Normal and kitchen_motion is Normal # same thing

# this is different
pantry_motion is Violated and kitchen_motion is Normal
```

There are also some symbolic global states that have magic behaviour (see the ooutput for each).  These are:

. nighttime_dark_mode
. toekicks_on_mode
. sunny
. cloudy


## MQTT Messages

MQTT messages are checked for being received on the default topic.  A line:

```
TOPIC [some topic name]
```

Sets the default topic for the .hgl file.

## Time clauses

Times can be specified as HH:MM:SS.  Time durations can be specified that way or as MM:SS or as a number followed by "hours/minutes/seconds".  E.g., you write "for 5 minutes" when modifying a state condition.

You may also specify a time using several astronomical times with "+" or "-" then a time duration:
. dawn
. sunrise | rising
. solar_noon
. sunset | setting
. dusk
. midnight


## Brace Expansions

When braces are used on the left-hand-side of a rule (the condition part) they imply expansion into separate rules. E.g.,

```
when HTTV_media_{all_off,all_on} do script.mh_b_vizio_tvs_*
```

is the same as these two MQTT rules:
```
when HTTV_media_all_off do script.mh_b_vizio_tvs_all_off
when HTTV_media_all_on do script.mh_b_vizio_tvs_all_on
```

(Which themselves, of course, are rewritten to two verbose YAML rules.) The "\*" character on the right hand side is used as a substitution location for the comma-separated value from inside the braces on the left-hand-side to be placed.


When braces are used on the right-hand-side, that is simple in-place expansion of the terms into multiple entities.  E.g.,
```
... do turn_off(light.{pantry,kitchen}_ceiling)
```
is the same as
```
... do turn_off(light.pantry_ceiling, light.kitchen_ceiling)
```
