import csv
from io import StringIO
import lxml.etree as ET
from operator import itemgetter
import re


def compact(string):
    'Remove empty lines from the HTML code.'
    return re.sub(r'\n(\s*\n)+', '\n', string)


def splitter(sep):
    return lambda x: x.split(sep)


def clean_special_chars(text):
    text = re.sub('[@$^_\xb0\xa8\u02c7\u20ac\u2020]', '', text)
    return text


def link(view, args):
    'Generates a link to a certain view with specified option settings.'

    def _str(value):
        if isinstance(value, list):
            return ','.join(map(str, value))
        elif isinstance(value, bool):
            return str(value).lower()
        else:
            return str(value)

    # get a dictionary of all non-default values specified for this link
    values = {
        key: _str(val)
        for key, val in args.model_dump().items()
        if val != args.model_fields[key].default
    }

    link = '/{}?'.format(view) + \
        '&'.join('{}={}'.format(key, val) for key, val in values.items())
    return link


def render_csv(rows, header=None, delimiter=','):
    stream = StringIO()
    writer = csv.writer(stream, delimiter=delimiter, lineterminator='\n')
    if header is not None:
        writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue()


def render_type_links(text):
    return re.sub('\[([^|\]]*)\|([^\]]*)\]',
                  '<a href="/poemlist?source=type&id=\\1">\\2</a>', text)


def escape_xml(string):
    return string.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def render_xml(string, refs=None, tag='ROOT'):

    def render_xml_node(node, ref_dict):
        text = [escape_xml(node.text)] if node.text is not None else []
        for c in node:
            if c.tag in ('I', 'U', 'SUP', 'SUB'):
                text.append('<{}>{}</{}>'.format(c.tag, render_xml_node(c, ref_dict), c.tag))
            elif c.tag == 'KA':
                content = render_xml_node(c, ref_dict)
                text.append(content[0] + '\u035c' + content[1:])
            elif c.tag == 'SMALLCAPS' and c.text is not None:
                text.append('<SMALL>{}</SMALL>'.format(c.text.upper()))
            elif c.tag in ('H', 'FR') and c.text is not None:
                text.append(c.text)
            elif c.tag == 'REFNR' and c.text is not None:
                reflinks = []
                for refnr in c.text.split(','):
                    if int(refnr) in ref_dict:
                        tooltip = ref_dict[int(refnr)]
                        reflinks.append('<a class="hover-text">'
                                        '<sup><small>{}</small></sup>'
                                        '<div class="tooltip-text" style="width: 200">{}</div>'
                                        '</a>'\
                                        .format(refnr, tooltip))
                    else:
                        reflinks.append('<sup>{}</sup>'.format(refnr))
                text.append('<sup>,</sup>'.join(reflinks))
            elif c.tag == 'REFR':
                text.append('<span class="refrain">{}</span>'.format(c.text))
            elif c.tag in ('O', 'PAG'):
                # skip the tag together with its content
                pass
            if c.tail is not None:
                text.append(c.tail)
        return ''.join(text)

    ref_dict = { r.num: r.text for r in refs } if refs is not None else {}
    node = ET.XML('<{}>{}</{}>'.format(tag, string, tag))
    return render_xml_node(node, ref_dict)


def remove_xml(string, tag='ROOT'):

    def remove_xml_node(node):
        text = [node.text] if node.text is not None else []
        for c in node:
            if c.tag in ('I', 'U', 'SUP', 'SUB', 'KA', 'SMALLCAPS', 'H', 'FR'):
                text.append(remove_xml_node(c))
            else:
                pass
            if c.tail is not None:
                text.append(c.tail)
        return ''.join(text)

    node = ET.XML('<{}>{}</{}>'.format(tag, string, tag))
    return remove_xml_node(node)


def print_type_list(poem, types):
    result = []
    for type_id in poem.type_ids + poem.minor_type_ids:
        t_ids = [type_id] + types[type_id].ancestors
        t_ids.reverse()
        result.append(' > '.join(types[x].name for x in t_ids))
    return '\n'.join(result)

def makecol(value, base, max_value):
    'Converts a numeric value to a color (higher value=darker color).'

    def _makecolcomp(value, base, max_value):
        result = hex(base + int((255-base)*(1-value/max_value)))[2:]
        if len(result) == 1:
            result = '0'+result
        return result

    if value is None:
        value = 1
    val_norm = min(value, max_value)
    val_norm = max(0, val_norm)
    base_rgb = (int(base[:2], base=16),
                int(base[2:4], base=16),
                int(base[4:6], base=16))
    r = _makecolcomp(val_norm, base_rgb[0], max_value)
    g = _makecolcomp(val_norm, base_rgb[1], max_value)
    b = _makecolcomp(val_norm, base_rgb[2], max_value)
    return '#'+r+g+b
