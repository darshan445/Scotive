# frozen_string_literal: true

module Api
  module V1
    class InvoicesController < Api::V1::BaseController
      def conversation
        result = ::Invoices::BuildConversation.execute(
          organization: current_organization,
          invoice_id: params[:id]
        )
        render_result(result, failure_status: :not_found)
      end

      def timeline
        result = ::Invoices::BuildTimeline.execute(
          organization: current_organization,
          invoice_id: params[:id]
        )
        render_result(result, failure_status: :not_found)
      end

      def action
        result = ::Invoices::ApplyAction.execute(
          organization: current_organization,
          invoice_id: params[:id],
          action: body_param("action"),
          due_date: body_param("due_date"),
          wait_until: body_param("wait_until") || body_param("expected_pay_date")
        )
        render_result(result, failure_status: missing_invoice?(result) ? :not_found : :unprocessable_content)
      end

      def draft_chase
        result = ::Invoices::DraftChase.execute(
          organization: current_organization,
          invoice_id: params[:id],
          note: body_param("note"),
          intent: body_param("intent")
        )
        render_result(result, failure_status: missing_invoice?(result) ? :not_found : :unprocessable_content)
      end

      def send_chase
        result = ::Invoices::SendChase.execute(
          organization: current_organization,
          invoice_id: params[:id],
          subject: body_param("subject"),
          body: body_param("body"),
          wait_until: body_param("wait_until")
        )
        render_result(result, failure_status: missing_invoice?(result) ? :not_found : :unprocessable_content)
      end

      private

      def body_param(key)
        request.request_parameters[key].presence || params[key]
      end

      def missing_invoice?(result)
        !result.success? && result.errors.to_s.match?(/not found/i)
      end
    end
  end
end
