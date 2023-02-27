# encoding=utf-8
import os
import json
import re
from collections import defaultdict
from my_rasa_sdk.events import SlotSet
from typing import Text, Dict, Any
from my_rasa_sdk import Action, Tracker
from my_rasa_sdk.executor import CollectingDispatcher
from py2neo import Graph
from markdownify import markdownify as md

p = 'data/Diseases_dic.txt'
disease_names = [i.strip() for i in open(p, 'r', encoding='UTF-8').readlines()]
graph = Graph('http://localhost:7474/', auth=("neo4j", "123456"))


class TireNode:
    def __init__(self):
        self.word_finish = False
        self.count = 0
        self.word = None
        self.entity_class = defaultdict(set)
        self.child = defaultdict(TireNode)


def read_json(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)


class Tire:
    def __init__(self):
        self.root = TireNode()

    def add(self, word, entity_class):
        curr_node = self.root
        for char in str(word).strip():
            curr_node = curr_node.child[char]
        curr_node.count += 1
        curr_node.word = word
        curr_node.entity_class[word].add(entity_class)
        curr_node.word_finish = True

    def search(self, words):
        entity_dic = {}
        for i in range(len(words)):
            word = words[i:]
            curr_node = self.root
            for char in word:
                curr_node = curr_node.child.get(char)
                if curr_node is not None and curr_node.word_finish == True:
                    entity_dic[curr_node.word] = curr_node.entity_class.get(curr_node.word)
                elif curr_node is None or len(curr_node.child) == 0:
                    break
        return entity_dic if entity_dic else ''


class MatchEntity:
    def __init__(self):
        self.tire = Tire()
        self.entity_dic = {}
        self.cur_dir = '/'.join(os.path.abspath(__file__).split('/')[:-1]) + '/entity_dict/'
        for file_name in [file for file in os.listdir(self.cur_dir) if file != '.DS_Store']:
            entity_name = file_name.split('.')[0]
            self.entity_dic[entity_name] = self.read_data(self.cur_dir + file_name)

        for name, entity_lis in self.entity_dic.items():
            for entity in entity_lis:
                self.tire.add(entity, name)

    def read_data(self, path):
        with open(path, 'r', encoding='utf-8') as file:
            return [word.strip() for word in file.readlines() if word.strip()]

    def match(self, words):
        entity_dic = self.tire.search(words)
        slot_list = []
        if entity_dic:
            for entity, class_set in entity_dic.items():
                for class_ in class_set:
                    slot_list.append(SlotSet(class_, entity))
                    return slot_list, entity_dic
        else:
            return slot_list, entity_dic


class parser_question():
    def __init__(self):
        self.num_limit = 20
        self.g = graph
        self.text_json = read_json('data/attribute.json')
        self.relation_dic = self.text_json['relation']
        self.com_relation_dic = self.text_json['com_relation']
        self.attribute_lis = self.text_json['attribute']

    def parser(self, entity, intent):
        parser_lis = []
        res_lis = []
        intent = '_'.join(str(intent).split('_')[1:])
        if intent in self.attribute_lis:
            sql = "MATCH (m:Disease) where m.name = '{}' return m.name, m.{}".format(entity, intent)
            parser_lis.append(sql)
        if intent in self.relation_dic:
            end_node = self.relation_dic.get(intent, '')
            if end_node:
                sql = "MATCH (m:Disease)-[r:{}]->(n:{}) where m.name = '{}' return m.name, r.name, n.name".format(
                    intent, end_node, entity)
                parser_lis.append(sql)
        if intent in self.com_relation_dic:
            relations = self.com_relation_dic.get(intent, '')
            if relations:
                sql1 = "MATCH (m:Disease)-[r:{}]->(n:{}) where m.name = '{}' return m.name, r.name, n.name".format(
                    relations[0], intent, entity)
                sql2 = "MATCH (m:Disease)-[r:{}]->(n:{}) where m.name = '{}' return m.name, r.name, n.name".format(
                    relations[1], intent, entity)
                parser_lis.append(sql1)
                parser_lis.append(sql2)
        for sql in parser_lis:
            res = self.g.run(sql).data()
            res_lis.extend(res)
        return res_lis


# parser = parser_question()
class ActionHelloWorld(Action):
    def name(self) -> Text:
        return "question_parser"

    def __init__(self):
        self.match = MatchEntity()
        # self.parser = parser_question()

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain):
        res_lis = []
        input_word = dict(tracker.latest_message)['text']
        slot_list, entity_dic = self.match.match(input_word)
        intent = tracker.latest_message['intent']['name']
        if entity_dic:
            for entity in entity_dic:
                res = parser_question().parser(entity, intent)
                res_lis.extend(res)
            dispatcher.utter_message(json.dumps(res_lis[0], ensure_ascii=False, indent=4))
        if not entity_dic:
            entity_lis = [tracker.get_slot(name) for name in
                          ['check', 'department', 'disease', 'drug', 'food', 'producer', 'symptom'] if
                          tracker.get_slot(name) is not None]
            if entity_lis:
                for entity in entity_lis:
                    res = parser_question().parser(entity, intent)
                    res_lis.extend(res)
                dispatcher.utter_message(json.dumps(res_lis[0], ensure_ascii=False, indent=4))
            else:
                return dispatcher.utter_message('我是机器人小八，有什么可以帮助你')  # 闲聊或反问
        return slot_list


class default_utter(Action):
    def name(self):  # type: () -> Text
        return 'defualt_action'

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain):
        dispatcher.utter_message('我是机器人小八，有什么可以帮助你')


def retrieve_disease_name(name):
    names = []
    name = '.*' + '.*'.join(list(name)) + '.*'
    pattern = re.compile(name)
    for i in disease_names:
        candidate = pattern.search(i)
        if candidate:
            names.append(candidate.group())
    return names


def make_button(title, payload):
    return {'title': title, 'payload': payload}


class ActionEcho(Action):
    def name(self) -> Text:
        return "action_echo"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        user_say = "You said: " + tracker.latest_message['text']
        dispatcher.utter_message(user_say)
        return []


class ActionFirst(Action):
    def name(self) -> Text:
        return "action_first"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        dispatcher.utter_template("utter_first", tracker)
        # dispatcher.utter_template("utter_howcanhelp", tracker)
        dispatcher.utter_message(md("您可以这样向我提问: "
                                    "<br/>头痛怎么办<br/>\
                              什么人容易头痛<br/>\
                              头痛吃什么药<br/>\
                              头痛能治吗<br/>\
                              头痛属于什么科<br/>\
                              头孢地尼分散片用途<br/>\
                              如何防止头痛<br/>\
                              头痛要治多久<br/>\
                              糖尿病有什么并发症<br/>\
                              糖尿病有什么症状"))
        return []


class ActionDonKnow(Action):
    def name(self) -> Text:
        return "action_donknow"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        dispatcher.utter_template("utter_donknow", tracker)
        # dispatcher.utter_template("utter_howcanhelp", tracker)
        dispatcher.utter_message(md("您可以这样向我提问: <br/>头痛怎么办<br/>\
                                      什么人容易头痛<br/>\
                                      头痛吃什么药<br/>\
                                      头痛能治吗<br/>\
                                      头痛属于什么科<br/>\
                                      头孢地尼分散片用途<br/>\
                                      如何防止头痛<br/>\
                                      头痛要治多久<br/>\
                                      糖尿病有什么并发症<br/>\
                                      糖尿病有什么症状"))
        return []


class ActionSearchTreat(Action):
    def name(self) -> Text:
        return "action_search_treat"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):

        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))

        possible_diseases = retrieve_disease_name(disease)
        # if len(possible_diseases) == 1 or sure == "true":
        if disease == pre_disease or len(possible_diseases) == 1:
            a = graph.run("match (a:Disease{name: $disease}) return a", disease=disease).data()[0]['a']
            if "intro" in a:
                intro = a['intro']
                template = "{0}的简介：{1}"
                retmsg = template.format(disease, intro)
            else:
                retmsg = disease + "暂无简介"
            dispatcher.utter_message(retmsg)
            if "treat" in a:
                treat = a['treat']
                template = "{0}的治疗方式有：{1}"
                retmsg = template.format(disease, "、".join(treat))
            else:
                retmsg = disease + "暂无常见治疗方式"
            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(make_button(d, '/search_treat{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 疾病相关的记录".format(disease))
        return []


class ActionSearchFood(Action):
    def name(self) -> Text:
        return "action_search_food"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))
        print("disease::::", disease)
        possible_diseases = retrieve_disease_name(disease)
        """ search_food db action here """
        food = dict()
        if disease == pre_disease or len(possible_diseases) == 1:
            m = [x['m.name'] for x in graph.run("match (a:Disease{name: $disease})-[:can_eat]->(m:Food) return m.name",
                                                disease=disease).data()]
            food['can_eat'] = "、".join(m) if m else "暂无记录"

            m = [x['m.name'] for x in graph.run("match (a:Disease{name: $disease})-[:not_eat]->(m:Food) return m.name",
                                                disease=disease).data()]

            food['not_eat'] = "、".join(m) if m else "暂无记录"

            retmsg = "在患 {0} 期间，可以食用：{1}，\n但不推荐食用：{2}". \
                format(disease, food['can_eat'], food['not_eat'])

            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(make_button(d, '/search_food{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 相关的饮食记录".format(disease))
        return []


class ActionSearchSymptom(Action):
    def name(self) -> Text:
        return "action_search_symptom"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))

        possible_diseases = retrieve_disease_name(disease)
        if disease == pre_disease or len(possible_diseases) == 1:
            a = [x['s.name'] for x in graph.run("MATCH (p:Disease{name: $disease})-[r:has_symptom]->\
                                                (s:Symptom) RETURN s.name", disease=disease).data()]
            template = "{0}的症状可能有：{1}"
            retmsg = template.format(disease, "、".join(a))
            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(make_button(d, '/search_symptom{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 相关的症状记录".format(disease))

        return []


class ActionSearchCause(Action):
    def name(self) -> Text:
        return "action_search_cause"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))

        possible_diseases = retrieve_disease_name(disease)
        if disease == pre_disease or len(possible_diseases) == 1:
            a = graph.run("match (a:Disease{name: $disease}) return a.cause", disease=disease).data()[0]['a.cause']
            if "treat" in a:
                treat = a['treat']
                template = "{0}的治疗方式有：{1}"
                retmsg = template.format(disease, "、".join(treat))
            else:
                retmsg = disease + "暂无该疾病的病因的记录"
            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(make_button(d, '/search_cause{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 相关的原因记录".format(disease))
        return []


class ActionSearchNeopathy(Action):
    def name(self) -> Text:
        return "action_search_neopathy"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))

        possible_diseases = retrieve_disease_name(disease)
        if disease == pre_disease or len(possible_diseases) == 1:
            a = [x['s.name'] for x in graph.run("MATCH (p:Disease{name: $disease})-[r:has_neopathy]->\
                                                (s:Disease) RETURN s.name", disease=disease).data()]
            template = "{0}的并发症可能有：{1}"
            retmsg = template.format(disease, "、".join(a))
            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(make_button(d, '/search_neopathy{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 相关的并发症记录".format(disease))
        return []


class ActionSearchDrug(Action):
    def name(self) -> Text:
        return "action_search_drug"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))

        possible_diseases = retrieve_disease_name(disease)
        if disease == pre_disease or len(possible_diseases) == 1:
            a = [x['s.name'] for x in graph.run("MATCH (p:Disease{name: $disease})-[r:can_use_drug]->\
                                                (s:Drug) RETURN s.name", disease=disease).data()]
            if a:
                template = "在患 {0} 时，可能会用药：{1}"
                retmsg = template.format(disease, "、".join(a))
            else:
                retmsg = "无 %s 的可能用药记录" % disease
            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(make_button(d, '/search_drug{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 相关的用药记录".format(disease))
        return []


class ActionSearchPrevention(Action):
    def name(self) -> Text:
        return "action_search_prevention"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))

        possible_diseases = retrieve_disease_name(disease)
        if disease == pre_disease or len(possible_diseases) == 1:
            a = graph.run("match (a:Disease{name: $disease}) return a.prevent", disease=disease).data()[0]
            if 'a.prevent' in a:
                prevent = a['a.prevent']
                template = "以下是有关预防 {0} 的知识：{1}"
                retmsg = template.format(disease, md(prevent.replace('\n', '<br/>')))
            else:
                retmsg = disease + "暂无常见预防方法"
            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(make_button(d, '/search_prevention{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 相关的预防记录".format(disease))
        return []


class ActionSearchDrugFunc(Action):
    def name(self) -> Text:
        return "action_search_drug_func"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        drug = tracker.get_slot("drug")
        if drug:
            a = [x['n.name'] for x in graph.run("match (n:Disease)-[:can_use_drug]->(a:Drug{name: $drug})"
                                                "return n.name", drug=drug).data()]
            template = "{0} 可用于治疗疾病：{1}"
            retmsg = template.format(drug, "、".join(a))
        else:
            retmsg = drug + " 在疾病库中暂无可治疗的疾病"
        dispatcher.utter_message(retmsg)
        return []


class ActionSearchDiseaseTreatTime(Action):
    def name(self) -> Text:
        return "action_search_disease_treat_time"  # treat_period

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))

        possible_diseases = retrieve_disease_name(disease)
        if disease == pre_disease or len(possible_diseases) == 1:
            a = graph.run("match (a:Disease{name: $disease}) return a", disease=disease).data()[0]['a']
            if "treat_period" in a:
                treat_period = a['treat_period']
                template = "{0}需要的治疗时间：{1}"
                retmsg = template.format(disease, treat_period)
            else:
                retmsg = disease + "暂无治疗时间的记录"
            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(
                    make_button(d, '/search_disease_treat_time{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 相关的治疗时间记录".format(disease))
        return []


class ActionSearchEasyGet(Action):
    def name(self) -> Text:
        return "action_search_easy_get"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))

        possible_diseases = retrieve_disease_name(disease)
        if disease == pre_disease or len(possible_diseases) == 1:
            a = graph.run("match (a:Disease{name: $disease}) return a", disease=disease).data()[0]['a']
            easy_get = a['easy_get']
            template = "{0}的易感人群是：{1}"
            retmsg = template.format(disease, easy_get)
            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(make_button(d, '/search_easy_get{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 相关的易感人群记录".format(disease))
        return []


class ActionSearchDiseaseDept(Action):
    def name(self) -> Text:
        return "action_search_disease_dept"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]):
        disease = tracker.get_slot("disease")
        pre_disease = tracker.get_slot("sure")
        print("pre_disease::::" + str(pre_disease))

        possible_diseases = retrieve_disease_name(disease)
        if disease == pre_disease or len(possible_diseases) == 1:
            a = graph.run("match (a:Disease{name: $disease})-[:belongs_to]->(s:Department) return s.name",
                          disease=disease).data()[0]['s.name']
            template = "{0} 属于 {1}"
            retmsg = template.format(disease, a)
            dispatcher.utter_message(retmsg)
        elif len(possible_diseases) > 1:
            buttons = []
            for d in possible_diseases:
                buttons.append(make_button(d, '/search_disease_dept{{"disease":"{0}", "sure":"{1}"}}'.format(d, d)))
            dispatcher.utter_button_message("请点击选择想查询的疾病，若没有想要的，请忽略此消息", buttons)
        else:
            dispatcher.utter_message("知识库中暂无与 {0} 疾病相关的科室记录".format(disease))
        return []
