"""Notification."""

import json
import frappe
from frappe import _
import requests
from frappe.model.document import Document
from frappe.utils.safe_exec import get_safe_globals, safe_exec
from frappe.integrations.utils import make_post_request
from frappe.desk.form.utils import get_pdf_link
from frappe.utils import add_to_date, nowdate, datetime
from string import Template
import asyncio

class WhatsAppNotification(Document):
    """Notification."""

    def validate(self):
        """Validate."""
        if self.notification_type == "DocType Event":
            fields = frappe.get_doc("DocType", self.reference_doctype).fields
            fields += frappe.get_all(
                "Custom Field",
                filters={"dt": self.reference_doctype},
                fields=["fieldname"]
            )
            if not any(field.fieldname == self.field_name for field in fields): # noqa
                frappe.throw(f"Field name {self.field_name} does not exists")
        if self.custom_attachment:
            if not self.attach and not self.attach_from_field:
                frappe.throw("Either <b>Attach</b> a file or add a <b>Attach from field</b> to send attachemt")

    def send_scheduled_message(self) -> dict:
        """Specific to API endpoint Server Scripts."""
        return
        """ 
        safe_exec(
            self.condition, get_safe_globals(), dict(doc=self)
        )
        language_code = frappe.db.get_value(
            "WhatsApp Templates", self.template,
            fieldname='language_code'
        )
        template_actual_name = frappe.db.get_value(
            "WhatsApp Templates", self.template,
            fieldname='actual_name'
        )
        doc = frappe.get_doc(self.reference_doctype, d.name).as_dict()

        self._contact_list=[]
        users = self.get_users_by_role("Blogger")
        for user  in users:
            append_if_not_exists(self._contact_list,get_user_contact_number(user))
     
        data = {
        "to": self._contact_list,
        "doc":doc
        }
        self.custom_notify(data)
        
        if language_code:
            for contact in self._contact_list:
                data = {
                    "messaging_product": "whatsapp",
                    "to": self.format_number(contact),
                    "type": "template",
                    "template": {
                        "name": template_actual_name,
                        "language": {
                            "code": language_code
                        },
                        "components": []
                    }
                }
                self.content_type = template.get("header_type", "text").lower()
                print("sche")
        """
    def send_template_message(self, doc: Document):
        """Specific to Document Event triggered Server Scripts."""
        if self.disabled:
            return

        doc_data = doc.as_dict()
        if self.condition:
            # check if condition satisfies
            if not frappe.safe_eval(
                self.condition, get_safe_globals(), dict(doc=doc_data)
            ):
                return

        template = frappe.db.get_value(
            "WhatsApp Templates", self.template,
            fieldname='*'
        )

        if template:
            data = {
                "messaging_product": "whatsapp",
                "to": self.format_number(doc_data[self.field_name]),
                "type": "template",
                "template": {
                    "name": template.actual_name,
                    "language": {
                        "code": template.language_code
                    },
                    "components": []
                }
            }

            # Pass parameter values
            if self.fields:
                parameters = []
                for field in self.fields:
                    value = doc_data[field.field_name]
                    if isinstance(doc_data[field.field_name], (datetime.date, datetime.datetime)):
                        value = str(doc_data[field.field_name])
                    parameters.append({
                        "type": "text",
                        "text": value
                    })

                data['template']["components"] = [{
                    "type": "body",
                    "parameters": parameters
                }]

            if self.attach_document_print:
                # frappe.db.begin()
                key = doc.get_document_share_key()  # noqa
                frappe.db.commit()
                print_format = "Standard"
                doctype = frappe.get_doc("DocType", doc_data['doctype'])
                if doctype.custom:
                    if doctype.default_print_format:
                        print_format = doctype.default_print_format
                else:
                    default_print_format = frappe.db.get_value(
                        "Property Setter",
                        filters={
                            "doc_type": doc_data['doctype'],
                            "property": "default_print_format"
                        },
                        fieldname="value"
                    )
                    print_format = default_print_format if default_print_format else print_format
                link = get_pdf_link(
                    doc_data['doctype'],
                    doc_data['name'],
                    print_format=print_format
                )

                filename = f'{doc_data["name"]}.pdf'
                url = f'{frappe.utils.get_url()}{link}&key={key}'

            elif self.custom_attachment:
                filename = self.file_name

                if self.attach_from_field:
                    file_url = doc_data[self.attach_from_field]
                    if not file_url.startswith("http"):
                        # get share key so that private files can be sent
                        key = doc.get_document_share_key()
                        file_url = f'{frappe.utils.get_url()}{file_url}&key={key}'
                else:
                    file_url = self.attach

                if file_url.startswith("http"):
                    url = f'{file_url}'
                else:
                    url = f'{frappe.utils.get_url()}{file_url}'

            if template.header_type == 'DOCUMENT':
                data['template']['components'].append({
                    "type": "header",
                    "parameters": [{
                        "type": "document",
                        "document": {
                            "link": url,
                            "filename": filename
                        }
                    }]
                })
            elif template.header_type == 'IMAGE':
                data['template']['components'].append({
                    "type": "header",
                    "parameters": [{
                        "type": "image",
                        "image": {
                            "link": url
                        }
                    }]
                })
            self.content_type = template.header_type.lower()

            # if self.custom_notification_recipient:
            #     receptors = []
            #     for role  in self.custom_notification_recipient:
            #         users = self.get_users_by_role(role.receiver_by_role)
            #         for user  in users:
            #             append_if_not_exists(receptors,get_user_contact_number(user))
            #     data["to"]=tuple(receptors)

            data["doc"]=doc_data
            users=[]
            contact_list=[]
            for role in self.roles:  
                users+= self.get_users_by_role(role.role)


            if not self.roles :
                self.custom_notify(data)
            else:
                for user  in users:
                    data["to"]=contact_list,get_user_contact_number(user)
                    self.custom_notify(data)

    def notify(self, data):
        """Notify."""
        settings = frappe.get_doc(
            "WhatsApp Settings", "WhatsApp Settings",
        )
        token = settings.get_password("token")

        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json"
        }
        try:
            success = False
            response = make_post_request(
                f"{settings.url}/{settings.version}/{settings.phone_id}/messages",
                headers=headers, data=json.dumps(data)
            )

            if not self.get("content_type"):
                self.content_type = 'text'

            frappe.get_doc({
                "doctype": "WhatsApp Message",
                "type": "Outgoing",
                "message": str(data['template']),
                "to": data['to'],
                "message_type": "Template",
                "message_id": response['messages'][0]['id'],
                "content_type": self.content_type
            }).save(ignore_permissions=True)

            frappe.msgprint("WhatsApp Message Triggered", indicator="green", alert=True)
            success = True

        except Exception as e:
            error_message = str(e)
            if frappe.flags.integration_request:
                response = frappe.flags.integration_request.json()['error']
                error_message = response.get('Error', response.get("message"))

            frappe.msgprint(
                f"Failed to trigger whatsapp message: {error_message}",
                indicator="red",
                alert=True
            )
        finally:
            if not success:
                meta = {"error": error_message}
            else:
                meta = frappe.flags.integration_request.json()
            frappe.get_doc({
                "doctype": "WhatsApp Notification Log",
                "template": self.template,
                "meta_data": meta
            }).insert(ignore_permissions=True)

    def custom_notify(self,data):
        asyncio.run(custom_notify_c(self,data))
    

    def on_trash(self):
        """On delete remove from schedule."""
        if self.notification_type == "Scheduler Event":
            frappe.delete_doc("Scheduled Job Type", self.name)

        frappe.cache().delete_value("whatsapp_notification_map")

    def after_insert(self):
        """After insert hook."""
        if self.notification_type == "Scheduler Event":
            method = f"frappe_whatsapp.utils.trigger_whatsapp_notifications_{self.event_frequency.lower().replace(' ', '_')}" # noqa
            job = frappe.get_doc(
                {
                    "doctype": "Scheduled Job Type",
                    "method": method,
                    "frequency": self.event_frequency
                }
            )

            job.insert()

    def format_number(self, number):
        """Format number."""
        if (number.startswith("+")):
            number = number[1:len(number)]

        return number


    def get_documents_for_today(self):
        """get list of documents that will be triggered today"""
        docs = []

        diff_days = self.days_in_advance
        if self.doctype_event == "Days After":
            diff_days = -diff_days

        reference_date = add_to_date(nowdate(), days=diff_days)
        reference_date_start = reference_date + " 00:00:00.000000"
        reference_date_end = reference_date + " 23:59:59.000000"

        doc_list = frappe.get_all(
            self.reference_doctype,
            fields="name",
            filters=[
                {self.date_changed: (">=", reference_date_start)},
                {self.date_changed: ("<=", reference_date_end)},
            ],
        )

        for d in doc_list:
            doc = frappe.get_doc(self.reference_doctype, d.name)
            self.send_template_message(doc)
            # print(doc.name)



    def get_users_by_role(self,role):
        return frappe.get_all('Has Role',filters={"role":role,"parenttype":"User"},fields=['parent'],pluck="parent")

@frappe.whitelist()
def call_trigger_notifications():
    """Trigger notifications."""
    try:
        # Directly call the trigger_notifications function
        trigger_notifications()  
    except Exception as e:
        # Log the error but do not show any popup or alert
        frappe.log_error(frappe.get_traceback(), "Error in call_trigger_notifications")
        # Optionally, you could raise the exception to be handled elsewhere if needed
        raise e

def trigger_notifications(method="daily"):
    if frappe.flags.in_import or frappe.flags.in_patch:
        # don't send notifications while syncing or patching
        return

    if method == "daily":
        doc_list = frappe.get_all(
            "WhatsApp Notification", filters={"doctype_event": ("in", ("Days Before", "Days After")), "disabled": 0}
        )
        for d in doc_list:
            alert = frappe.get_doc("WhatsApp Notification", d.name)
            alert.get_documents_for_today()
           

def get_user_contact_number(user_email):
    return frappe.get_value("User", {"name": user_email}, "phone")  # Get the contact linked to the user


def append_if_not_exists(my_list, item):
    if item not in my_list and item!=None:
        my_list.append(item)
    return my_list

def get_document_url(doctype, docname):
    # Construct the base URL
    base_url = frappe.utils.get_url()
    doc = frappe.get_doc(doctype,docname)
    # Create the document URL
    doc_url = f"{base_url}{doc.get_url()}"
    return doc_url


async def custom_notify_c(self, data):
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    settings = frappe.get_doc(
    "WhatsApp Settings",
    "WhatsApp Settings",
    )
    token = settings.get_password("token")

    url = f"{settings.url}chat"

    template = Template(self.code)

    message = template.substitute(data["doc"])
    
    # data["doc"]["description"] = html2text.html2text(data["doc"]["description"])
    if (data["doc"]["doctype"] == "ToDo") and 'reference_type' in (data["doc"]):
        doc= frappe.get_doc(data["doc"]["reference_type"],data["doc"]["reference_name"])
        doc_url = frappe.utils.get_url() + doc.get_url()
        data["doc"] = doc.as_dict()
    else:
        doc= frappe.get_doc(data["doc"]["doctype"],data["doc"]["name"])
        doc_url = frappe.utils.get_url() + doc.get_url()
        data["doc"] = doc.as_dict()


    msg = frappe.render_template(message,data["doc"])
    msg+="\n"+str(doc_url)

    dt={}
    dt["token"]=token
    dt["to"]=data["to"]
    dt["body"]=msg
    
    response = requests.request("POST", url, data=dt, headers=headers)
    if hasattr(response,"id"):
        self.message_id = response["id"]