#!/usr/bin/env python3
# Copyright (C) 2019 Greg J. Badros <badros@gmail.com>
# Distributed under the MIT License -- Use at your own risk!
#
# pip3 install lark-parser
# pip3 install braceexpand

from lark import Lark, Transformer, v_args
import sys
import re
import copy
import yaml
import logging
import pprint
import argparse
from pathlib import Path
from braceexpand import braceexpand

ap = argparse.ArgumentParser()

ap.add_argument("-d", "--debug", dest="debug",
                help="Set default logging level to DEBUG",
                action="store_true")
ap.add_argument("-b", "--base_url", dest="base_url",
                help="Base URL for Home Assistant, e.g., https://....")
args = ap.parse_known_args()

LOG_LEVEL = logging.INFO

if args[0].debug:
    LOG_LEVEL = logging.DEBUG

HTTP_BASE_URL = "http://localhost:8123"
if args[0].base_url:
    HTTP_BASE_URL = args[0].base_url

_LOGGER = logging.getLogger(sys.argv[0])
logging.basicConfig(level=LOG_LEVEL)
console = logging.StreamHandler()
console.setLevel(LOG_LEVEL)

input_lines = []
out = None


def expand_star(expansion, text):
    return text.replace('*', expansion)


def media_cleanups(service):
    service = service.replace('media_volume', 'volume')
    service = service.replace('channel_down', 'next_track')
    return service


def minutes_from_time_duration(args):
    if isinstance(args, dict):
        unit = args.keys()[0]
        val = int(args.values()[0])
        if unit == 'minutes':
            return val
        elif unit == 'seconds':
            return val/60
        elif unit == 'hours':
            return val*60
        else:
            raise "Unknown unit"
    s = [int(a) for a in args.split(":")]
    if len(s) == 3:
        return s[0] * 60 + s[1] + s[2]/60
    elif len(s) == 2:
        return s[0] + s[1]/60
    return s[0]/60


def text_from_meta(m):
    if m.line == m.end_line:
        ec = m.end_column - 1
    else:
        ec = None
    return input_lines[m.line-1][m.column-1:ec]


def lines_from_meta(m):
    if m.line == m.end_line:
        return " (line %d)" % (m.line)
    return " (lines %d to %d)" % (m.line, m.end_line)


hass_grammar = r"""

  start: _rule+

  _rule: when             // .mwd
       | when_mqtt
       | when_fires
       | when_template
       | power_control    // .mpc
       | time_range       // .tba
       | mqtt_topic_designation

  mqtt_topic_designation: "TOPIC" MQTT_TOPIC

  MQTT_TOPIC: /[\/_0-9a-zA-Z]+/

  when_mqtt: "when" mqtt_message [condition_clause] "do" action

  when_fires: "when" event "fires" condition_clause? "do" action

  // entity_state may braceexpand into multiple separate rules
  // entity_state's entity_id defaults to sensor._
  // action may have '*' replacements (with media_volume->volume substitution)
  when: "when" entity_state for_clause? condition_clause? "do" action else_clause?

  when_template: "when" "{{" trigger_template "}}" condition_clause? "do" action

  else_clause: "else" state_value for_clause? "do" action

  mqtt_message: BRACE_EXPANDED_WORD

  event: BRACE_EXPANDED_WORD

  entity_state: simple_entity_state
              | multiple_entity_state
              | condis_entity_state

  entity_state_condition: simple_entity_state
                        | multiple_entity_state
                        | condis_entity_state

  simple_entity_state: BRACE_EXPANDED_ENTITY ("is"|"==") state_value [ "with" with_attr_clause ] ( "and" with_attr_clause ) *

  with_attr_clause: "*." ATTRIBUTE "==" state_value

  ATTRIBUTE: /[_a-zA-Z][_0-9a-zA-Z]*/

  multiple_entity_state: state_conjunction
                       | state_disjunction

  state_conjunction: ENTITY ("is"|"==") state_value (/and/ entity_state)+

  state_disjunction: ENTITY ("is"|"==") state_value (/or/ entity_state)+

  condis_entity_state: entity_disjunction "is" state_value
                     | entity_conjunction "is" state_value

  entity_disjunction: ENTITY ( "or" ENTITY )+

  entity_conjunction: ENTITY ( "and" ENTITY )+

  GLOBAL_STATE: "nighttime_dark_mode"
              | "toekicks_on_mode"
              | "sunny"
              | "cloudy"

  ?state_value: RAW_VALUE
             | "\"" QUOTED_VALUE "\""
             | "'" QUOTED_VALUE "'"

  RAW_VALUE: /[_0-9a-zA-Z.]+/

  QUOTED_VALUE: /[^"'\n]+/

  DOMAIN: /[_0-9a-zA-Z]+/

  ENTITY: /([_0-9a-zA-Z\*]+\.)?[_0-9a-zA-Z]+/

  BRACE_EXPANDED_ENTITY: /([_0-9a-zA-Z\*]+\.)?[{},_0-9a-zA-Z]+/

  for_clause: "for" time_duration

  time_duration: HH_MM_SS
               | MM_SS
               | NUMBER /hours/
               | NUMBER /minutes/
               | NUMBER /seconds/

  trigger_template: JINJA_TEMPLATE

  condition_clause: /(while|when)/ entity_state_condition
                  | /(while|when)/ GLOBAL_STATE

  action: _service_name
        | _service_name "(" service_params ")"

  // service_name may have '*' replacements
  _service_name: SERVICE_NAME

  // service_params may braceexpand inline (not separate rules)
  // or '*' just backreferences the same entities mentioned in the trigger
  service_params: /\*/
                 | service_nvp ( "," service_nvp )*
                 | BRACE_EXPANDED_ENTITY

  service_nvp: /[_0-9a-zA-Z.\*]+/ ( "=" state_value ) ?

  BRACE_EXPANDED_WORD: /[_0-9a-zA-Z,.{}]+/

  SERVICE_NAME: /(\*|([_0-9a-zA-Z,]+\.)?[_0-9a-zA-Z,.{}]+\*?)/

  JINJA_TEMPLATE: /.+/

  HH_MM_SS: /[0-9]?[0-9]:[0-9][0-9]:[0-9][0-9]/

  MM_SS: /[0-9]?[0-9]:[0-9][0-9]/

  NUMBER: /[0-9]+(\.[0-9]+)?/

  // TIME RANGE RULE (.tba)
  time_range: "from" time "to" time with_clause start_clause end_clause
            | time "..." time with_clause start_clause end_clause

  time: TIME_LITERAL
      | TIME_LOGICAL ( PLUSMINUS time_duration )?

  TIME_LITERAL: /[0-9]?[0-9]:[0-9][0-9]([ap]m)?/

  TIME_LOGICAL: "solar_noon"
              | "sunrise" | "sunset"
              | "dawn" | "dusk"
              | "midnight" | "noon"
              | "rising" | "setting"

  PLUSMINUS: /[+-]/

  with_clause: "with" ENTITY
             | "with" entity_state

  start_clause: "start" condition_clause ":" action

  end_clause: "end" ":" action


  // POWER RULE (.mpc)
  // lhs does not need brace expansion
  // rhs may be braceexpanded inline
  power_control: ENTITY "powered_by" BRACE_EXPANDED_ENTITY
               | /\*/ "off_at" time

  COMMENT : "#" /.*/

  %import common.WS
  %ignore WS
  %ignore COMMENT

"""


def Merge(dict1, dict2):
    res = {**dict1, **dict2}
    return res


def MergeAll(dicts):
    res = {}
    for d in dicts:
        res = {**res, **d}
    return res


def replace_action_wildcards_from(else_service, service):
    if else_service == '*':
        return service
    if '*.' in else_service:
        return service + else_service[2:]
    return else_service


def output_automation_rule(dict, name=None):
    if name is None:
        name = dict.pop('_name', 'TODO_unique_id')
    out.write(yaml.dump([{'alias': name,
                          'hide_entity': True,
                          'initial_state': True,
                          **dict}], sort_keys=False, width=240))
    out.write("\n")


def output_comment():
    pass


def template_from_condis(connector, vals, is_val):
    answer = "{{"
    jc = " " + connector + " "
    answer += jc.join("is_state(\"%s\", \"%s\")" % (v, is_val) for v in vals)
    answer += "}}"
    return answer


def service_default(default, service):
    if '.' in service:
        return service
    if not default:
        default = 'homeassistant'
    return default + "." + service


def domain_from(entity):
    if entity is False:
        return False
    if "." in entity:
        return entity.split('.')[0]
    return None


class HassOutputter(Transformer):
    mqtt_topic = 'vantage/misc'
    all_power_entities = []

    def mqtt_topic_designation(self, args):
        _LOGGER.debug("mqtt_topic_designation: %s", str(args[0]))
        HassOutputter.mqtt_topic = str(args[0])

    @v_args(tree=True)
    def when_mqtt(self, t):
        args = t.children
        # when_mqtt: "when" mqtt_message condition_clause? "do" action
        _LOGGER.debug("when_mqtt: %s", pprint.pformat(args))
        d = MergeAll(args)
        msg = d['trigger'].pop('_message')
        exp = d.pop('_expansions', [''])
        default_domain = d.pop('_default_domain', None)
        for (i, e) in enumerate(exp):
            new_d = copy.deepcopy(d)
            exp_msg = expand_star(e, msg)
            name = exp_msg + lines_from_meta(t.meta)
            new_d['condition'] = {
                'condition': 'template',
                'value_template':
                "{{ trigger.payload | trim == \"%s\" }}" % exp_msg}
            action = new_d['action']
            action['service'] = media_cleanups(
                expand_star(e, action['service']))
            service_domain = domain_from(action['service'])
            if service_domain:
                if domain_from(action.get('entity_id', False)) is None:
                    action['entity_id'] = (service_domain +
                                           "." + action['entity_id'])
            else:
                action['service'] = service_default(
                    default_domain, action['service'])
            output_automation_rule(new_d, name)

    @v_args(tree=True)
    def when_fires(self, t):
        args = t.children
        # when_mqtt: "when" mqtt_message condition_clause? "do" action
        _LOGGER.debug("when_fires: %s", pprint.pformat(args))
        d = MergeAll(args)
        default_domain = d.pop('_default_domain', None)
        exp = d.pop('_expansions', None)
        action = d['action']
        if isinstance(action, dict):
            action['service'] = service_default(
                default_domain, action['service'])
            service_domain = domain_from(action['service'])
            if service_domain:
                if domain_from(action.get('entity_id', False)) is None:
                    action['entity_id'] = (service_domain +
                                           "." + action['entity_id'])
        if not exp:
            name = "when_fires_" + d['trigger']['event_type'] + lines_from_meta(t.meta)
            output_automation_rule(d, name)
        else:
            for (i, e) in enumerate(exp):
                name = "when_fires_" + e + lines_from_meta(t.meta)
                new_d = copy.deepcopy(d)
                dt = new_d['action'][0]['data_template']
                mci = dt['media_content_id']
                dt['media_content_id'] = expand_star(e, mci)
                new_d['trigger']['event_type'] = expand_star(
                    e, new_d['trigger']['event_type'])
                output_automation_rule(new_d, name + " #" + str(i))

    def when_template(self, args):
        output_comment()
        _LOGGER.debug("when_template: %s", args)

    @v_args(tree=True)
    def when(self, t):
        args = t.children
        _LOGGER.debug("when - TREE: %s", t.pretty())
        _LOGGER.debug("when: %s", args)
        name = "when__" + lines_from_meta(t.meta)
        d = MergeAll(args)
        d.pop('_entity_summary', None)
        # gotta move the for clause into the trigger
        if d.get('for'):
            for_clause = d['for']
            del d['for']
            d['trigger']['for'] = for_clause
        default_domain = d.pop('_default_domain', None)
        action = d['action']
        action['service'] = service_default(
            default_domain, action['service'])

        else_clause = d.pop('_else', None)
        d2 = None
        else_vta = d.pop('_else_value_template_args', None)
        when_or_while = d.pop('_when_or_while', None)
        # if thee was an else clause, we need to copy the first rule,
        # invert the trigger (possibly using demorgan's law) and
        # substitue wild cards
        if else_clause:
            if len(else_clause) == 2:
                for_clause = {}
                action_clause = else_clause[1]
            else:
                for_clause = else_clause[1]
                action_clause = else_clause[2]
            else_name = "ELSE " + name
            d2 = copy.deepcopy(d)
            # 'while' means apply the condition to the else clause, too
            # 'when' means only have the condition on the primary
            if when_or_while == 'when':
                del d2['condition']
            if else_vta is not None:
                d2['trigger']['value_template'] = template_from_condis(
                    else_vta[0], else_vta[1], else_clause[0])
            else:
                d2['trigger'] = {**d2['trigger'], 'to': else_clause[0], **for_clause}
            d2 = {**d2, **action_clause}
            d2['action']['service'] = replace_action_wildcards_from(
                d2['action']['service'], d['action']['service'])
            d2['action']['service'] = service_default(
                default_domain, d2['action']['service'])
            if d2['action'].get('entity_id') == '*':
                d2['action']['entity_id'] = d['action']['entity_id']
        exp = d['trigger'].pop('_expansions', None)
        if not exp:
            output_automation_rule(d, name)
            if d2:
                output_automation_rule(d2, else_name)
            return
        else:
            entity_wc = d['trigger'].pop('_entity_id_wc', None)
            for (i, e) in enumerate(exp):
                new_d = copy.deepcopy(d)
                entity = service_default('sensor', expand_star(e, entity_wc))
                new_d['trigger']['entity_id'] = entity
                action = new_d['action']
                action['service'] = expand_star(e, action['service'])
                if action.get('entity_id'):
                    action['entity_id'] = expand_star(e, action['entity_id'])
                output_automation_rule(new_d, name + " #" + str(i))
                if d2:
                    new_d2 = copy.deepcopy(d2)
                    new_d2['trigger']['entity_id'] = entity
                    output_automation_rule(new_d2, else_name + " #" + str(i))

    def power_control(self, args):
        if args[0] == '*':
            time_off = args[1]
            # TODO: handle all entities turning off at time_off
            rule_all_off = {
                '_name': sys.argv[1] + ' media_power all_off',
                'trigger': {**time_off},
                'action': {
                    'service': 'homeassistant.turn_off',
                    'entity_id': ",".join(HassOutputter.all_power_entities)
                }
            }
            result = [rule_all_off]
        else:
            media_zone = service_default('media_player', args[0])
            powered_by = service_default('switch', args[1]['entity_id'])
            result = []
            state_rule_on = {'platform': 'state',
                             'entity_id': media_zone,
                             'to': 'playing',
                             'from': 'idle'}
            rule_power_on = {
                '_name': media_zone + " turn power on",
                'initial_state': True,
                'trigger': [state_rule_on,
                            {**copy.deepcopy(state_rule_on),
                             'from': 'off'},
                            {**copy.deepcopy(state_rule_on),
                             'from': 'paused'}],
                'action': {
                    'service': 'homeassistant.turn_on',
                    'entity_id': powered_by
                }
            }
            state_rule_off = {'platform': 'state',
                              'entity_id': media_zone,
                              'from': 'playing',
                              'to': 'idle',
                              'for': {'minutes': 15}}
            rule_power_off = {
                '_name': media_zone + " turn power off_at",
                'initial_state': True,
                'trigger': [state_rule_off,
                            {**copy.deepcopy(state_rule_off), 'to': 'off'}],
                'action': {
                    'service': 'homeassistant.turn_off',
                    'entity_id': powered_by
                }
            }
            HassOutputter.all_power_entities.append(powered_by)
            result = [rule_power_on, rule_power_off]
        for r in result:
            output_automation_rule(r)
        return

    # TODO: avoid using base_url explicitly below
    def action(self, args):
        _LOGGER.debug("action: %s", args)
        if args[0] == 'play_doorbird_media':
            entities = ",".join([service_default('media_player', e)
                                 for e in args[1]['entity_id'].split(",")])
            return {
                'action':
                [{
                    'service': 'media_player.play_media',
                    'data_template': {
                        'entity_id': entities,
                        'media_content_id':
                        HTTP_BASE_URL +
                        "/api/camera_proxy_stream/camera.*_live?token={{states.camera.*_live.attributes.access_token}}",
                        'media_content_type': 'image/jpg'
                    }
                }, {
                    'delay': '00:00:30',
                }, {
                    'service': 'media_player.turn_off',
                    'entity_id': entities,
                }]
            }
        if len(args) > 1:
            return {'action': {'service': args[0], **args[1]}}
        else:
            return {'action': {'service': args[0]}}

    @v_args(inline=True)
    def BRACE_EXPANDED_WORD(self, args):
        word = str(args)
        p = re.compile(r'\{.*\}')
        m = p.search(word)
        result = {}
        if m:
            expansions = list(braceexpand(m.group()))
            word = word[:m.start()] + '*' + word[m.end():]
            result['_expansions'] = expansions
        result["_word"] = word
        _LOGGER.debug("BEW: %s -> %s", args, result)
        return result

    @v_args(inline=True)
    def ENTITY(self, entity):
        result = str(entity)
        _LOGGER.debug("SN: %s -> %s", entity, result)
        return result

    @v_args(inline=True)
    def BRACE_EXPANDED_ENTITY(self, args):
        entity = str(args)
        p = re.compile(r'{.*}')
        m = p.search(entity)
        result = {}
        if m:
            expansions = list(braceexpand(m.group()))
            entity_wc = entity[:m.start()] + '*' + entity[m.end():]
            result['_expansions'] = expansions
            result['_entity_id_wc'] = entity_wc
            result['entity_id'] = ",".join(list(braceexpand(entity)))
        else:
            result['entity_id'] = entity
        _LOGGER.debug("BEE: %s -> %s", args, result)
        return result

    def RAW_VALUE(self, val):
        return str(val)

    def ATTRIBUTE(self, val):
        return str(val)

    def QUOTED_VALUE(self, val):
        return str(val)

    @v_args(inline=True)
    def SERVICE_NAME(self, args):
        service = str(args)
        expansions = None
        p = re.compile(r'{.*}')
        m = p.search(service)
        result = {}
        if m:
            expansions = list(braceexpand(m.group()))
            service = service[:m.start()] + '*' + service[m.end():]
            result['_expansions'] = expansions
            result['_service'] = service
        else:
            result = service
        _LOGGER.debug("SN: %s -> %s", args, result)
        return result

    def HH_MM_SS(self, args):
        return args

    def MM_SS(self, args):
        return "00:" + args

    def for_clause(self, args):
        result = {'for': args[0]}
        _LOGGER.debug("for_clause: %s -> %s", args, result)
        return result

    def time_duration(self, args):
        if len(args) > 1:
            result = {str(args[1]): args[0]}
        else:
            result = str(args[0])
        _LOGGER.debug("time_duration: %s -> %s", args, result)
        return result

    def TIME_LITERAL(self, args):
        result = {'_time_literal': str(args)}
        _LOGGER.debug("TIME_LITERAL: %s -> %s", args, result)
        return result

    def TIME_LOGICAL(self, args):
        t = str(args)
        if t == 'solar_noon':
            t = 'noon'
        elif t == 'sunrise':
            t = 'rising'
        elif t == 'sunset':
            t = 'setting'
        result = {'_time_logical': t}
        _LOGGER.debug("TIME_LOGICAL: %s -> %s", args, result)
        return result

    def PLUSMINUS(self, args):
        _LOGGER.debug("PLUSMINUS: %s", args)
        return str(args)

    def time(self, args):
        if args[0].get("_time_logical"):
            sun_event = args[0]['_time_logical']
            suffix = ""
            if len(args) > 1:
                suffix = " %s %s" % (args[1],
                                     minutes_from_time_duration(args[2]))
            result = {
                'platform': 'template',
                'value_template':
                "{{ (as_timestamp(states.sensor.time.last_changed)/60)|round "
                "== (as_timestamp(states.sun.sun.attributes.next_%s)/60)|round %s }}"
                % (sun_event, suffix)}
        else:
            time_literal = args[0]['_time_literal']
            result = {'platform': 'time', 'at': time_literal}
        _LOGGER.debug("time: %s -> %s", args, result)
        return result

    def NUMBER(self, args):
        return int(args)

    def mqtt_message(self, args):
        _LOGGER.debug("mqtt_message: %s", args)
        result = {'trigger': {'platform': 'mqtt',
                              'topic': HassOutputter.mqtt_topic,
                              '_message': args[0]['_word']},
                  'condition': None}
        if args[0].get('_expansions'):
            result['_expansions'] = args[0]['_expansions']
        return result

    def event(self, args):
        _LOGGER.debug("event: %s", args)
        result = {'trigger': {'platform': 'event',
                              'event_type': args[0]['_word']}}
        if args[0].get('_expansions'):
            result['_expansions'] = args[0]['_expansions']
        return result

    def condition_clause(self, args):
        result = {'condition': args[1], '_when_or_while': str(args[0])}
        _LOGGER.debug("condition_clause: %s -> %s", args, result)
        return result

    def else_clause(self, args):
        _LOGGER.debug("else_clause: %s", args)
        return {'_else': args}

    def service_nvp(self, args):
        if len(args) == 2:
            result = {str(args[0]): args[1]}
        else:
            result = str(args[0])
        _LOGGER.debug("service_nvp: %s -> %s", args, result)
        return result

    # { 'entity_id': list }
    # { 'entity_id': '*' }
    # { 'entity_id': list, 'data': { nvps } }
    def service_params(self, args):
        entities = []
        others = {}
        for a in args:
            if isinstance(a, dict) and a.get('entity_id'):
                entities.append(a.get('entity_id'))
            elif not isinstance(a, dict):
                entities.append(a)
            else:
                others = {**others, **a}
        result = {}
        if len(entities) > 0:
            result['entity_id'] = ",".join(entities)
        if len(others) > 0:
            result['data'] = others
        _LOGGER.debug("service_params: %s -> %s", args, result)
        return result

    def GLOBAL_STATE(self, args):
        if args == 'sunny':
            result = {'condition': 'template',
                      'value_template':
                      '{{ is_state("sensor.weather_conditions", "Clear") '
                      'or is_state("sensor.weather_conditions", "Partly Cloudy") }}'}
        elif args == 'cloudy':
            result = {'condition': 'template',
                      'value_template':
                      '{{ is_state("sensor.weather_conditions", "Cloudy") '
                      'or is_state("sensor.weather_conditions", "Rainy") }}'}
        else:
            result = {'condition': 'template',
                      'value_template': '{{ states("%s") == "1.0" }}' % args}
        return result

    def simple_entity_state(self, args):
        result = {**args[0], 'to': args[1]}
        if len(args) > 2:
            entity = args[0].get('entity_id')
            c = {}
            result['_condition'] = c
            c['condition'] = 'template'
            vt = "{{ " + " and ".join(
                "states.%s.attributes[\"%s\"] == \"%s\"" % (
                    entity, a[0], a[1]) for a in args[2:]) + " }}"
            c['value_template'] = vt
            _LOGGER.debug("simple_entity_state: %s -> %s", args, result)
        return result

    def with_attr_clause(self, args):
        _LOGGER.debug("with_attr_clause: %s", args)
        return args

    def entity_state(self, args):
        _LOGGER.debug("entity_state: %s", args)
        if args[0].get('entity_id'):
            args[0]['entity_id'] = service_default(
                'sensor', args[0]['entity_id'])
        or_vals = args[0].get('_template_or')
        and_vals = args[0].get('_template_and')
        is_val = args[0].get('_template_is')
        if or_vals:
            result = {'trigger':
                      {'platform': 'template',
                       'value_template':
                       template_from_condis(
                           'or', or_vals, is_val)},
                      '_else_value_template_args':
                      ['and', or_vals, None],
                      '_entity_summary':
                      ",".join(or_vals) + " is " + is_val}
        elif and_vals:
            result = {'trigger':
                      {'platform': 'template',
                       'value_template':
                       template_from_condis(
                           'and', and_vals, is_val)},
                      '_else_value_template_args':
                      ['or', and_vals, None],
                      '_entity_summary':
                      ",".join(and_vals) + " is " + is_val}
        else:
            result = {'trigger': {'platform': 'state', **args[0]}}
            if result['trigger'].get('_condition'):
                result['condition'] = result['trigger']['_condition']
                del result['trigger']['_condition']
        return result

    def entity_state_condition(self, args):
        _LOGGER.debug("entity_state_condition: %s", args)
        if args[0].get('entity_id'):
            args[0]['entity_id'] = service_default(
                'sensor', args[0]['entity_id'])
        to_state = args[0].pop('to', None)
        if to_state:
            args[0]['state'] = to_state
        or_vals = args[0].get('_template_or')
        and_vals = args[0].get('_template_and')
        is_val = args[0].get('_template_is')
        if or_vals:
            result = {'condition': 'template',
                      'value_template':
                      template_from_condis(
                          'or', or_vals, is_val),
                      '_else_value_template_args':
                      ['and', or_vals, None],
                      '_entity_summary':
                      ",".join(or_vals) + " is " + is_val}
        elif and_vals:
            result = {'condition': 'template',
                      'value_template':
                      template_from_condis(
                          'and', and_vals, is_val),
                      '_else_value_template_args':
                      ['or', and_vals, None],
                      '_entity_summary':
                      ",".join(and_vals) + " is " + is_val}
        else:
            result = {'condition': 'state', **args[0]}
            if result.pop('_condition', None):
                result['condition'] = result['_condition']
        return result

    def entity_disjunction(self, args):
        result = {'_template_or': [service_default('sensor', a) for a in args]}
        _LOGGER.debug("entity_disjunction: %s -> %s", args, result)
        return result

    def entity_conjunction(self, args):
        result = {'_template_and':
                  [service_default('sensor', a) for a in args]}
        _LOGGER.debug("entity_conjunction: %s -> %s", args, result)
        return result

    def condis_entity_state(self, args):
        result = {**args[0], '_template_is': str(args[1])}
        _LOGGER.debug("condis_entity_state: %s -> %s", args, result)
        return result

    @v_args(tree=True)
    def time_range(self, t):
        args = t.children
        _LOGGER.debug("time_range: %s", t.pretty())
        start_time = args[0]
        end_time = args[1]
        with_entity = args[2]
        start_action = args[3]
        start_action['action']['entity_id'] = with_entity
        end_action = args[4]
        end_action['action']['entity_id'] = with_entity
        name = text_from_meta(t.meta)
        when_or_while = args[3].get('_when_or_while')
        if when_or_while:
            del args[3]['_when_or_while']
        start_rule = {
            '_name': "start " + name,
            'initial_state': True,
            'hide_entity': True,
            'trigger': {
                **start_time
            },
            **start_action
        }
        end_rule = {
            '_name': "end " + name,
            'initial_state': True,
            'hide_entity': True,
            'trigger': {
                **end_time
            },
            **end_action
        }
        if when_or_while == 'while':
            end_rule['condition'] = start_rule['condition']
        output_automation_rule(start_rule)
        output_automation_rule(end_rule)
        return args

    def with_clause(self, args):
        if isinstance(args[0], dict):
            result = args[0].get('entity_id')
        else:
            result = args[0]
        _LOGGER.debug("with_clause: %s -> %s", args, result)
        return result

    def start_clause(self, args):
        result = MergeAll(args)
        _LOGGER.debug("start_clause: %s -> %s", args, result)
        return result

    def end_clause(self, args):
        _LOGGER.debug("end_clause: %s", args)
        return args[0]


if __name__ == '__main__':
    parser = Lark(hass_grammar, start="start", ambiguity="explicit",
                  propagate_positions=True)

    infile = args[1][0]

    if not infile:
        exit(-1)

    dump = False

    with open(infile, "r") as f:
        input = f.read()

    input_lines = input.splitlines()

    t = parser.parse(input)

    if dump:
        print(parser.parse(input).pretty())
    else:
        outfile = Path(infile).with_suffix(".yaml")
        if len(args[1]) > 1:
            outfile = args[1][1]
        _LOGGER.debug("outfile = %s", outfile)
        with open(outfile, "w") as o:
            o.write("## THIS FILE WAS GENERATED BY hass-hgl-to-yaml.py\n")
            o.write("## " + " ".join(sys.argv) + "\n\n")
            out = o
            HassOutputter(visit_tokens=True).transform(t)
