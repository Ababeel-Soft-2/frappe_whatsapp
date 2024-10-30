# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt
import json
import frappe
import string
import random
import requests
from frappe.utils.pdf import get_pdf
from frappe.model.document import Document
from frappe.integrations.utils import make_post_request


class WhatsAppMessage(Document):
    """Send whats app messages."""

    def before_insert(self):
        """Send message."""
        if self.type == "Outgoing" and self.message_type != "Template":
            if self.attach and not self.attach.startswith("http"):
                link = frappe.utils.get_url() + "/" + self.attach
            else:
                link = self.attach

            data = {
                "messaging_product": "whatsapp",
                "to": self.format_number(self.to),
                "type": self.content_type,
            }
            if self.is_reply and self.reply_to_message_id:
                data["context"] = {"message_id": self.reply_to_message_id}
            if self.content_type in ["document", "image", "video"]:
                data[self.content_type.lower()] = {
                    "link": link,
                    "caption": self.message,
                }
            elif self.content_type == "reaction":
                data["reaction"] = {
                    "message_id": self.reply_to_message_id,
                    "emoji": self.message,
                }
            elif self.content_type == "text":
                data["text"] = {"preview_url": True, "body": self.message}

            elif self.content_type == "audio":
                data["text"] = {"link": link}
            try:
                self.custom_notify(data)
                self.status = "Success"
            except Exception as e:
                self.status = "Failed"
                frappe.throw(f"Failed to send message {str(e)}")
        elif self.type == "Outgoing" and self.message_type == "Template" and not self.message_id:
            self.send_template()

    def send_template(self):
        """Send template."""
        template = frappe.get_doc("WhatsApp Templates", self.template)
        data = {
            "messaging_product": "whatsapp",
            "to": self.format_number(self.to),
            "type": "template",
            "template": {
                "name": template.actual_name or template.template_name,
                "language": {"code": template.language_code},
                "components": [],
            },
        }

        if template.sample_values:
            field_names = template.field_names.split(",") if template.field_names else template.sample_values.split(",")
            parameters = []
            template_parameters = []

            ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)
            for field_name in field_names:
                value = ref_doc.get_formatted(field_name.strip())

                parameters.append({"type": "text", "text": value})
                template_parameters.append(value)

            self.template_parameters = json.dumps(template_parameters)

            data["template"]["components"].append(
                {
                    "type": "body",
                    "parameters": parameters,
                }
            )

        if template.header_type and template.sample:
            field_names = template.sample.split(",")
            header_parameters = []
            template_header_parameters = []

            ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)
            for field_name in field_names:
                value = ref_doc.get_formatted(field_name.strip())
                
                header_parameters.append({"type": "text", "text": value})
                template_header_parameters.append(value)

            self.template_header_parameters = json.dumps(template_header_parameters)

            data["template"]["components"].append({
                "type": "header",
                "parameters": header_parameters,
            })

        self.custom_notify(data)

    def notify(self, data):
        """Notify."""
        settings = frappe.get_doc(
            "WhatsApp Settings",
            "WhatsApp Settings",
        )
        token = settings.get_password("token")

        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        }
        try:
            response = make_post_request(
                f"{settings.url}/{settings.version}/{settings.phone_id}/messages",
                headers=headers,
                data=json.dumps(data),
            )
            self.message_id = frappe.flags.integration_request.json()["id"]
            pass

        except Exception as e:
            res = frappe.flags.integration_request.json()["error"]
            error_message = res.get("Error", res.get("message"))
            frappe.get_doc(
                {
                    "doctype": "WhatsApp Notification Log",
                    "template": "Text Message",
                    "meta_data": frappe.flags.integration_request.json(),
                }
            ).insert(ignore_permissions=True)

            frappe.throw(msg=error_message, title=res.get("error_user_title", "Error"))



    def custom_notify(self, data):
        
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        settings = frappe.get_doc("WhatsApp Settings","WhatsApp Settings")
        token = settings.get_password("token")
        url = f"{settings.url}{self.content_type_switch()}"
        dt={}
        dt["token"]=token
        dt["to"]=data["to"]
        
        if self.is_reply:
            dt["msgId"]=self.message_id
            dt["type"]="reaction"
        
        if data["type"]=="text":
            dt["body"]=data["text"]["body"]
        
        elif data["type"]==self.content_type_switch():
            dt[self.content_type_switch()]=data[self.content_type_switch()]["link"]
            dt["caption"]=data[self.content_type_switch()]["caption"]
            
            if dt[self.content_type_switch()] and  not dt[self.content_type_switch()].startswith("http"):
                dt[self.content_type_switch()] = frappe.utils.get_url() + "/" + dt[self.content_type_switch()]
        
        if data["type"]=="document":
            dt["filename"]=self.label
    
        #response = requests.request("POST", url, data=dt, headers=headers)
       
        try:
            response = make_post_request(
            url,headers=headers,data=dt,
            )
            self.message_id = response["message"]["id"]
        except Exception as e:
            frappe.get_doc(
            {
            "doctype": "WhatsApp Notification Log",
            "template": "Text Message",
            "meta_data": frappe.flags.integration_request.json(),
            }
            ).insert(ignore_permissions=True)

       

        # self.message_id = response.json()["id"]
    
    def content_type_switch(self):
        if self.content_type == "text":
            return "chat"
        else:
            return self.content_type


    def format_number(self, number):
        """Format number."""
        if number.startswith("+"):
            number = number[1 : len(number)]

        return number



def on_doctype_update():
    frappe.db.add_index("WhatsApp Message", ["reference_doctype", "reference_name"])


@frappe.whitelist()
def send_template(to, reference_doctype, reference_name, template):
    try:
        doc = frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": to,
            "type": "Outgoing",
            "message_type": "Template",
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "content_type": "text",
            "template": template
        })

        doc.save()
    except Exception as e:
        raise e


@frappe.whitelist()
def send_doc_pdf(to, doctype,docname,print_format):

    pdf_url =generate_invoice(doctype,docname,print_format)
    if pdf_url and not pdf_url.startswith("http"):
        pdf_url = frappe.utils.get_url() + "/" + pdf_url
    else:
        pdf_url = pdf_url
    try:
        doc = frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": to,
            "type": "Outgoing",
            "message_type": "Manual",
            "reference_doctype": doctype,
            "reference_name": docname,
            "content_type": "document",
            "attach": pdf_url,
            "label":doctype,
            "message":docname
        })

        doc.save()
    except Exception as e:
        raise e


def generate_invoice(doctype,docname,print_format):
    res = ''.join(random.choices(string.ascii_letters,k=7))
    pdf =frappe.get_print(doctype,docname,print_format,as_pdf=True)
    return save_pdf_to_frappe(f"{res}.pdf",pdf)
 
def save_pdf_to_frappe(file_name, content):
    # Create a new File document
    file_doc = frappe.get_doc({
        'doctype': 'File',
        'file_name': file_name,
        'content': content,
        'is_private': 0,  # 0 for public files, 1 for private
        'attached_to_doctype': '',  # Optional: specify if attached to another doctype
        'attached_to_name': ''       # Optional: specify the name of the attached document
    })
    # Save the document
    file_doc.save()
    # Return the file URL
    return file_doc.file_url