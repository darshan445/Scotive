# frozen_string_literal: true

module Api
  module V1
    module Onboarding
      class ModalDismissalsController < Api::V1::BaseController
        def create
          result = ::Onboarding::DismissModal.execute(organization: current_organization)
          render_result(result)
        end
      end
    end
  end
end
