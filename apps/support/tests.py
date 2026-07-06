from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from apps.orders.models import Order
from apps.support.models import GrievanceComplaint, SupportTicket, TicketMessage

User = get_user_model()


class SupportTeamCommunicationTests(TestCase):
    def setUp(self):
        # Customer
        self.customer = User.objects.create_user(
            username="customer_support",
            email="cust@example.com",
            password="pass",
            phone_number="9845555555",
            is_phone_verified=True,
        )
        # Support Agent
        self.agent = User.objects.create_user(
            username="agent_user",
            email="agent@example.com",
            password="pass",
            phone_number="9846666666",
            is_staff=True,
            role=User.Role.ADMIN,
        )
        # Ticket
        self.ticket = SupportTicket.objects.create(
            user=self.customer,
            subject="Delivery delay inquiry",
            channel=SupportTicket.Channel.LIVE_CHAT,
        )
        self.message1 = TicketMessage.objects.create(
            ticket=self.ticket,
            sender=self.customer,
            sender_type=TicketMessage.SenderType.CUSTOMER,
            message="Hello, when will my order arrive?",
        )

    def test_agent_console_requires_staff(self):
        # Unauthenticated returns 302
        res = self.client.get(reverse("support:agent_console"))
        self.assertEqual(res.status_code, 302)

        # Customer returns 403
        self.client.force_login(self.customer)
        res = self.client.get(reverse("support:agent_console"))
        self.assertEqual(res.status_code, 403)

        # Agent returns 200
        self.client.force_login(self.agent)
        res = self.client.get(reverse("support:agent_console"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("tickets", res.context)

    def test_agent_can_reply_to_ticket(self):
        self.client.force_login(self.agent)
        res = self.client.post(
            reverse("support:agent_ticket_reply", kwargs={"ticket_id": self.ticket.id}),
            data={
                "message": "We are dispatched, arriving within 30 minutes!",
                "status": "waiting_customer",
            },
        )
        self.assertEqual(res.status_code, 302)

        # Verify message created and ticket updated
        reply = TicketMessage.objects.filter(ticket=self.ticket, sender_type=TicketMessage.SenderType.AGENT).first()
        self.assertIsNotNone(reply)
        self.assertEqual(reply.message, "We are dispatched, arriving within 30 minutes!")
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "waiting_customer")
        self.assertIsNotNone(self.ticket.first_response_at)

    def test_customer_can_reply_to_ticket_thread(self):
        self.client.force_login(self.customer)
        res = self.client.post(
            reverse("support:ticket_customer_reply", kwargs={"ticket_id": self.ticket.id}),
            data={"message": "Great, thank you!"},
        )
        self.assertEqual(res.status_code, 302)
        reply = TicketMessage.objects.filter(ticket=self.ticket, sender=self.customer).last()
        self.assertEqual(reply.message, "Great, thank you!")

    def test_complaint_list_displays_tickets_and_grievances(self):
        self.client.force_login(self.customer)
        res = self.client.get(reverse("support:complaint_list"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("support_tickets", res.context)
        self.assertIn(self.ticket, res.context["support_tickets"])
