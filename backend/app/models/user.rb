# frozen_string_literal: true

class User < ApplicationRecord
  belongs_to :organization

  devise :database_authenticatable, :registerable, :recoverable,
         :rememberable, :trackable, :validatable,
         :jwt_authenticatable, jwt_revocation_strategy: JwtDenylist
end
